import pytest
from aihawk.academic_exeter_react_select import select
from aihawk.academic_browser import PortalPreparationError

def test_exeter_hidden_native_select_without_clicking_overlay():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="chrome",headless=True)
        page=browser.new_page()
        page.set_content("""
        <label for="country">Country of current residence</label>
        <select id="country" style="display:none">
          <option value="uk" selected>UK - England</option>
          <option value="ir">Iran, Islamic Republic of</option>
        </select>
        <div style="position:fixed;inset:0;z-index:99">Overlay</div>
        """)
        r=select(page,{"type":"react_select","label_contains":"Country of current residence",
                       "option":"Iran, Islamic Republic of","source_evidence":"reviewed"})
        assert r["control"]=="native_select"
        assert page.locator("#country").input_value()=="ir"
        browser.close()
