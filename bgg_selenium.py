"""Shared Selenium helpers used by both scrape_rankings.py and
scrape_metadata.py: building the driver, dismissing the cookie-consent
banner, and logging in to BGG.

Factored out so the two scrapers don't duplicate this logic.
"""

import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

import config


# --- Consent banner --------------------------------------------------------

# Candidate selectors for the cookie/consent "Accept" button, tried in order.
# BGG uses Google's fundingchoices CMP ("I'm OK with that").
CONSENT_BUTTON_SELECTORS = [
    (By.XPATH, "//p[@class='fc-button-label' and normalize-space(.)=\"I'm OK with that\"]/ancestor::button"),
    (By.XPATH, "//p[contains(@class,'fc-button-label')]/ancestor::button"),
    (By.CSS_SELECTOR, ".fc-cta-consent"),
    (By.CSS_SELECTOR, "button.fc-button.fc-cta-consent"),
    (By.ID, "onetrust-accept-btn-handler"),
    (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
    (By.XPATH, "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept')]"),
    (By.XPATH, "//button[contains(translate(text(), 'AGREE', 'agree'), 'agree')]"),
    (By.XPATH, "//button[contains(translate(text(), 'CONSENT', 'consent'), 'consent')]"),
]


# --- Login -----------------------------------------------------------------

LOGIN_URL = "https://boardgamegeek.com/login"
LOGIN_USERNAME_SELECTOR = (By.ID, "inputUsername")
LOGIN_PASSWORD_SELECTOR = (By.ID, "inputPassword")
LOGIN_SUBMIT_SELECTOR = (By.XPATH, "//button[normalize-space(.)='Sign In']")
LOGIN_TIMEOUT = 40

# How many times to (re)try loading the login page if the form doesn't appear.
LOGIN_ATTEMPTS = 3


def make_driver(headless):
    """Create and return a Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _try_consent_buttons(driver):
    """Try each consent selector in the CURRENT frame. Return True on success."""
    for by, selector in CONSENT_BUTTON_SELECTORS:
        try:
            button = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((by, selector))
            )
            button.click()
            print("Consent banner dismissed via {}={}".format(by, selector))
            time.sleep(1.0)
            return True
        except TimeoutException:
            continue
        except Exception as e:
            print("Consent click failed for {}={}: {}".format(by, selector, e))
            continue
    return False


def dismiss_consent(driver):
    """Accept/close the cookie-consent banner if present (main doc or iframe)."""
    time.sleep(2.0)
    if _try_consent_buttons(driver):
        return True
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        found = _try_consent_buttons(driver)
        driver.switch_to.default_content()
        if found:
            return True
    print("No consent banner found (or already accepted).")
    return False


def login(driver, username, password):
    """Log in to BGG so that authenticated pages become accessible.

    Retries loading the login page a few times, because after dismissing the
    consent banner the Angular login form sometimes takes a while (or a reload)
    to appear.
    """
    print("Logging in to BGG as", username, "...")

    username_field = None
    for attempt in range(1, LOGIN_ATTEMPTS + 1):
        driver.get(LOGIN_URL)
        # Consent banner usually only appears on the very first load.
        dismiss_consent(driver)
        try:
            username_field = WebDriverWait(driver, LOGIN_TIMEOUT).until(
                EC.element_to_be_clickable(LOGIN_USERNAME_SELECTOR)
            )
            break  # form is here
        except TimeoutException:
            print("  Login form not ready (attempt {}/{}), retrying ...".format(
                attempt, LOGIN_ATTEMPTS))
            time.sleep(2.0)
    if username_field is None:
        raise RuntimeError(
            "Login form (inputUsername) never appeared after {} attempts. "
            "BGG may be slow or blocking; try again, or run with "
            "SELENIUM_HEADLESS=False to watch.".format(LOGIN_ATTEMPTS))

    password_field = driver.find_element(*LOGIN_PASSWORD_SELECTOR)
    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)

    submit = WebDriverWait(driver, LOGIN_TIMEOUT).until(
        EC.element_to_be_clickable(LOGIN_SUBMIT_SELECTOR)
    )
    submit.click()

    try:
        WebDriverWait(driver, LOGIN_TIMEOUT).until(EC.staleness_of(password_field))
    except TimeoutException:
        raise RuntimeError(
            "Login may have failed: the login form is still present. "
            "Check your BGG_USERNAME / BGG_PASSWORD in .env."
        )
    print("Login successful.")


def make_logged_in_driver():
    """Convenience: build a driver and log in, reading credentials from config.

    Returns the driver (caller is responsible for driver.quit()).
    """
    username = config.BGG_USERNAME
    password = config.BGG_PASSWORD
    if not username or not password:
        raise RuntimeError(
            "BGG_USERNAME and BGG_PASSWORD must be set in your .env file. "
            "See .env.example."
        )
    driver = make_driver(config.SELENIUM_HEADLESS)
    login(driver, username, password)
    return driver