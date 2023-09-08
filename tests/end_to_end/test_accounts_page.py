import datetime
import os
import re

from playwright.sync_api import expect


def _bypass_sign_in(end_to_end_context):
    # Open a new page and go to the staging site.
    page = end_to_end_context.new_page()
    page.goto(os.getenv("NOTIFY_E2E_TEST_URI"))

    sign_in_button = page.get_by_role("link", name="Sign in")

    # Test trying to sign in. Because we are loading the email and password
    sign_in_button.click()

    # Wait for the next page to fully load.
    page.wait_for_load_state("domcontentloaded")
    return page


def test_accounts_page(end_to_end_context):

    page = _bypass_sign_in(end_to_end_context)

    # Check the page title exists and matches what we expect.
    # TODO this value depends on how many pre-existing services there are.  If 0, "Choose service", else "Dashboard"
    expect(page).to_have_title(re.compile("Choose service"))


def test_add_new_service_workflow(end_to_end_context):
    page = end_to_end_context.new_page()
    page.goto(os.getenv("NOTIFY_E2E_TEST_URI"))

    #sign_in_button = page.get_by_role("link", name="Sign in")

    # Test trying to sign in. Because we are loading the email and password
    #sign_in_button.click()

    # Wait for the next page to fully load.
    page.wait_for_load_state("domcontentloaded")


    # Prepare for adding a new service later in the test.
    current_date_time = datetime.datetime.now()
    new_service_name = "E2E Federal Test Service {now} - {browser_type}".format(
        now=current_date_time.strftime("%m/%d/%Y %H:%M:%S"),
        browser_type=end_to_end_context.browser.browser_type.name,
    )

    accounts_uri = "{}accounts".format(os.getenv("NOTIFY_E2E_TEST_URI"))

    page.goto(accounts_uri)

    # Check to make sure that we've arrived at the next page.
    page.wait_for_load_state("domcontentloaded")

    # Check to make sure that we've arrived at the next page.
    # Check the page title exists and matches what we expect.
    expect(page).to_have_title(re.compile("Choose service"))

    # Check for the sign in heading.
    sign_in_heading = page.get_by_role("heading", name="Choose service")
    expect(sign_in_heading).to_be_visible()

    # Retrieve some prominent elements on the page for testing.
    add_service_button = page.get_by_role(
        "button", name=re.compile("Add a new service")
    )

    expect(add_service_button).to_be_visible()

    existing_service_link = page.get_by_role("link", name=new_service_name)

    # Check to see if the service was already created - if so, we should fail.
    # TODO:  Figure out how to make this truly isolated, and/or work in a
    #        delete service workflow.
    expect(existing_service_link).to_have_count(0)

    # Click on add a new service.
    add_service_button.click()

    # Check to make sure that we've arrived at the next page.
    page.wait_for_load_state("domcontentloaded")

    # Check for the sign in heading.
    about_heading = page.get_by_role("heading", name="About your service")
    expect(about_heading).to_be_visible()

    # Retrieve some prominent elements on the page for testing.
    service_name_input = page.locator('xpath=//input[@name="name"]')
    federal_radio_button = page.locator('xpath=//input[@value="federal"]')
    state_radio_button = page.locator('xpath=//input[@value="state"]')
    other_radio_button = page.locator('xpath=//input[@value="other"]')
    add_service_button = page.get_by_role("button", name=re.compile("Add service"))

    expect(service_name_input).to_be_visible()
    expect(federal_radio_button).to_be_visible()
    expect(state_radio_button).to_be_visible()
    expect(other_radio_button).to_be_visible()
    expect(add_service_button).to_be_visible()

    # Fill in the form.
    service_name_input.fill(new_service_name)
    print(f"page before federal radio_button click {page}")
    expect(federal_radio_button).to_be_enabled()
    # Trying to click directly on the radio button resulted in a "not in viewport error" and this is the
    # suggested workaround.  Googling, the reason seems to be that there might be some (invisible?) css positioned
    # above the radio button itself.
    page.click("text='Federal government'")

    # Click on add service.
    add_service_button.click()

    # Check to make sure that we've arrived at the next page.
    page.wait_for_load_state("domcontentloaded")

    # Check for the service name title and heading.
    service_heading = page.get_by_text(new_service_name)
    expect(service_heading).to_be_visible()
    expect(page).to_have_title(re.compile(new_service_name))