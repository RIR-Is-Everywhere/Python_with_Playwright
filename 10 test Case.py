import os
import re

import pytest
from playwright.sync_api import Page, expect, sync_playwright


BASE_URL = "https://www.saucedemo.com/"
ERROR_SELECTOR = '[data-test="error"]'


@pytest.fixture
def page() -> Page:
    headless = os.getenv("PW_HEADLESS", "true").lower() in {"1", "true", "yes"}
    slow_mo = int(os.getenv("PW_SLOW_MO_MS", "0"))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = browser.new_page()
        page.goto(BASE_URL)
        yield page
        browser.close()


def login(page: Page, username: str, password: str) -> None:
    page.fill("#user-name", username)
    page.fill("#password", password)
    page.click("#login-button")


def login_as_standard_user(page: Page) -> None:
    login(page, "standard_user", "secret_sauce")
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))


def add_products(page: Page, count: int) -> None:
    buttons = page.locator(".inventory_item button")
    for index in range(count):
        buttons.nth(index).click()


def open_cart(page: Page) -> None:
    page.locator(".shopping_cart_link").click()


def start_checkout(page: Page) -> None:
    open_cart(page)
    page.locator('[data-test="checkout"]').click()


def fill_checkout(page: Page, first_name: str, last_name: str, postal_code: str) -> None:
    page.fill('[data-test="firstName"]', first_name)
    page.fill('[data-test="lastName"]', last_name)
    page.fill('[data-test="postalCode"]', postal_code)
    page.locator('[data-test="continue"]').click()


def error_text(page: Page) -> str:
    return page.locator(ERROR_SELECTOR).inner_text().lower()


def run_test_case(page: Page, case_id: str) -> None:
    if case_id == "TC_01":
        login_as_standard_user(page)
        expect(page.locator(".title")).to_have_text("Products")
    elif case_id == "TC_02":
        login(page, "invalid_user", "wrong_pass")
        expect(page.locator(ERROR_SELECTOR)).to_be_visible()
        assert "do not match" in error_text(page)
    elif case_id == "TC_03":
        login(page, "", "")
        expect(page.locator(ERROR_SELECTOR)).to_be_visible()
        assert "username is required" in error_text(page)
    elif case_id == "TC_04":
        login_as_standard_user(page)
        expect(page.locator(".inventory_item")).to_have_count(6)
        expect(page.locator(".inventory_item_name").first).to_be_visible()
        expect(page.locator(".inventory_item_price").first).to_be_visible()
        expect(page.locator(".inventory_item button").first).to_have_text("Add to cart")
    elif case_id == "TC_05":
        login_as_standard_user(page)
        add_products(page, 1)
        expect(page.locator(".shopping_cart_badge")).to_have_text("1")
        expect(page.locator(".inventory_item button").first).to_have_text("Remove")
    elif case_id == "TC_06":
        login_as_standard_user(page)
        add_products(page, 3)
        expect(page.locator(".shopping_cart_badge")).to_have_text("3")
    elif case_id == "TC_07":
        login_as_standard_user(page)
        add_products(page, 1)
        page.locator(".inventory_item button").first.click()
        expect(page.locator(".shopping_cart_badge")).to_have_count(0)
        expect(page.locator(".inventory_item button").first).to_have_text("Add to cart")
    elif case_id == "TC_08":
        login_as_standard_user(page)
        add_products(page, 1)
        open_cart(page)
        expect(page).to_have_url(re.compile(r".*/cart\.html$"))
        expect(page.locator(".cart_item")).to_have_count(1)
    elif case_id == "TC_09":
        login_as_standard_user(page)
        add_products(page, 1)
        start_checkout(page)
        fill_checkout(page, "", "", "")
        expect(page.locator(ERROR_SELECTOR)).to_be_visible()
        assert "first name is required" in error_text(page)
    elif case_id == "TC_10":
        login_as_standard_user(page)
        add_products(page, 1)
        start_checkout(page)
        fill_checkout(page, "John", "Doe", "12345")
        page.locator('[data-test="finish"]').click()
        expect(page).to_have_url(re.compile(r".*/checkout-complete\.html$"))
        expect(page.locator(".complete-header")).to_have_text("Thank you for your order!")


@pytest.mark.parametrize("case_id", [f"TC_{i:02d}" for i in range(1, 11)])
def test_saucedemo_cases(page: Page, case_id: str) -> None:
    run_test_case(page, case_id)
