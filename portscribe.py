#!/usr/bin/env python

import sys
import os
import re
import platform
from pathlib import Path
import pickle
import time
import getopt
from dataclasses import dataclass
import pyotp

import qbittorrentapi
os.environ['QBITTORRENTAPI_DO_NOT_VERIFY_WEBUI_CERTIFICATE'] = "1"

import selenium
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import dotenv
dotenv.load_dotenv()
ws_username = os.environ["ws_username"]
ws_password = os.environ["ws_password"]
ws_otp = os.environ.get("ws_otp")
qbt_username = os.environ["qbt_username"]
qbt_password = os.environ["qbt_password"]
qbt_host = os.environ["qbt_host"]
qbt_port = os.environ["qbt_port"]

def get_otp():
    if ws_otp is not None:
        totp = pyotp.TOTP(ws_otp)
        return totp.now()

URL = 'https://windscribe.com/myaccount#portforwards'
driver = None
quiet = False

@dataclass
class Settings:
    headless: bool = True

def verbose_print(msg):
    if not quiet:
        print(msg)

def make_browser(settings: Settings):
    global driver

    options = Options()
    if settings.headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")

    if not driver:
        try:
            driver = webdriver.Chrome(options=options)
        except:
            verbose_print("Trying to download Chrome")
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=ChromeDriverManager().install(), options=options)
    return driver

def acquire_lock():
    if platform.system() == 'Windows':
        import msvcrt
        fd = os.open("lock", os.O_RDWR | os.O_CREAT, 0o644)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")  # ensure at least 1 byte
            os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fd = os.open("lock", os.O_WRONLY | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_bt():
    client = qbittorrentapi.Client(host=qbt_host, port=qbt_port, username=qbt_username, password=qbt_password)
    client.auth_log_in()
    if not client.application.preferences:
        raise Exception("Testing qbittorrent API connection failed!")
    verbose_print('BT ok')

def nav(url, force=False):
    if force or driver.current_url != url:
        driver.get(url)

def wait_until_not_selector(selector, secs=5):
    return WebDriverWait(driver, secs).until_not(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

def wait_until_selector(selector, secs=5):
    return WebDriverWait(driver, secs).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

def is_logged_in():
    try:
        nav(URL)
        driver.find_element('css selector', '#myaccountpage')
        return True
    except NoSuchElementException as ex:
        return False

def login():
    nav('https://www.windscribe.com/login');
    otp = get_otp()
    if otp is not None:
        try:
            driver.find_element("css selector", '.have_2fa').click()
        except NoSuchElementException as ex:
            print(driver.page_source)
            raise ex
        time.sleep(2)
    wait_until_selector('.login-box #username')
    user = driver.find_element("css selector", '.login-box #username')
    passwd = driver.find_element("css selector", '.login-box #pass')
    user.send_keys(ws_username)
    passwd.send_keys(ws_password)
    if otp is not None:
        verbose_print('Got OTP key')
        wait_until_selector('.login-box #code')
        code = driver.find_element('css selector', '.login-box #code')
        button = driver.find_element("css selector", '#login_button')
        otp = get_otp()
        code.send_keys(otp)
        button.click()
        code.send_keys(Keys.RETURN)
        verbose_print('Sent form')
    else:
        button = driver.find_element("css selector", '#login_button')
        passwd.send_keys(Keys.RETURN)
        verbose_print('Sent form')
    wait_until_selector('#myaccountpage')
    verbose_print('Got to panel')
    wait_until_selector("#menu-ports")
    verbose_print('Switching tab')
    driver.find_element("css selector", '#menu-ports').click()
    wait_until_selector("#ports-main-tab")
    verbose_print('Got to ports tab')


def maybe_login():
    if is_logged_in():
        verbose_print('Reusing the cookie')
    else:
        verbose_print("Login to Windscribe") 
        login()

def load_cookies():
    if Path("cookies.pkl").exists():
        if not driver.current_url.startswith('https://windscribe.com/'):
            nav("https://windscribe.com/")
        verbose_print('Loading cookies')
        with open("cookies.pkl", "rb") as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
        nav(URL)

def save_cookies():
    filename = "cookies.pkl"
    with open(f"{filename}~", "wb") as f:
        pickle.dump(driver.get_cookies(), f)
        f.flush()
        os.fsync(f.fileno())
    time.sleep(3)
    os.replace(f"{filename}~", filename)

def parse_duration(s: str):
    m = re.match(r"(?:(\d+)\s+days?\s+)?(\d{1,2}):(\d{1,2}):(\d{1,2})", s)
    if m:
        verbose_print('Parse remaining duration')
        days = int(m.group(1) or 0)
        hours, minutes, seconds = map(int, m.group(2,3,4))
        return seconds + 60*minutes + 3600*hours + 86400*days
    else:
        verbose_print(f"Couldn't parse remaining duration '{s}'")
        return None

def get_port_reservation():
    nav(URL); wait_until_selector("#portforwardpage")
    try:
        wait_until_selector("#epf-countdown", secs=5)
    except TimeoutException:
        return None, None
    try:
        s = driver.find_element('css selector', '#epf-countdown').text
    except NoSuchElementException:
        return None, None
    return parse_duration(s), s

def is_on_port_forward_page():
    try:
        driver.find_element('css selector', '#portforwardpage')
        return True
    except NoSuchElementException:
        return False

def get_port():
    load_cookies()
    maybe_login()

    if not is_on_port_forward_page():
        nav(URL); wait_until_selector("#portforwardpage")

    save_cookies()
    verbose_print('Saved cookies')
    r, s = get_port_reservation()
    verbose_print(f"Time remaining {s}")

    if r is None or r < 86400:
        nav(URL); wait_until_selector('#portforwardpage')

        verbose_print("Deleting old port")
        driver.execute_script('staticIPS.deleteEphPort();')
        wait_until_not_selector('#epf-countdown')

        verbose_print("Request new port")
        driver.execute_script('staticIPS.postEphPort(true);')
        wait_until_selector('#epf-countdown')
    else:
        verbose_print("Not replacing the port")

    port = driver.find_element('css selector', '#ports-main-tab .pf-details span.pf-ext')
    verbose_print(f"Port {port.text}")
    return int(port.text)

def set_port(new_port):
    client = qbittorrentapi.Client(host=qbt_host, port=qbt_port, username=qbt_username, password=qbt_password)
    client.auth_log_in()
    prefs = client.app.preferences
    if 'listen_port' not in prefs or prefs['listen_port'] != new_port:
        verbose_print('Set port')
        prefs['listen_port'] = new_port
        client.app.set_preferences(prefs)
    else:
        verbose_print('Port already set')
    verbose_print("All done.")

def usage(ret=2):
    lines = [
        "Usage:",
        f" {sys.argv[0]} [options]",
        "",
        "Auto-renew Windscribe port redirect and notify qBittorrent.",
        "",
        "Options:",
        "  --no-headless		run with Chromium GUI for debugging",
        "  --quiet | -q		don't report on progress",
        "  --help		this text",
    ]
    for line in lines:
        print(line)
    exit(ret)

if __name__ == "__main__":
    optlist, args = getopt.getopt(sys.argv[1:], '+qh', [ 'no-headless', 'help', "quiet" ])
    settings = Settings()

    if args:
        print(f"bad argument '{args[0]}'", file=sys.stderr)
        usage()
    for k, v in optlist:
        match k:
            case '--no-headless':
                settings.headless = False
            case '--quiet' | '-q':
                quiet = True
            case '--help' | '-h':
                usage(ret=0)
            case _:
                print(f"bad argument '{k}'", file=sys.stderr)
                usage()

    acquire_lock()
    test_bt()
    driver = make_browser(settings)
    try:
        port = get_port()
        set_port(port)
        verbose_print('Exiting chromedriver')
    finally:
        if driver is not None:
            driver.quit()

# eof
