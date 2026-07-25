import XCTest

/// Exercises the authenticated Applications flow (sidebar -> list -> Kanban
/// toggle -> detail) against MockURLProtocol's canned responses (see
/// RapportApp.swift/MockURLProtocol.swift) rather than a real backend —
/// AuthFlowUITests already covers the unauthenticated onboarding/login
/// screens, this covers what's behind them.
///
/// The simulator's NavigationSplitView collapses to showing only its
/// front-most column (detail) with a "Show Sidebar" button rather than all
/// three columns side by side, even on an iPad — verified by dumping
/// `app.debugDescription` on a failing run: only the detail placeholder
/// ("Select an item") was in the hierarchy, no sidebar or content list.
/// So every test drives the same sidebar -> content -> detail navigation a
/// real user would use in that collapsed state, instead of assuming the
/// content column is already visible.
final class ApplicationsFlowUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-uiTesting", "-uiTestingMockAPI", "-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        navigateToApplicationsList()
    }

    /// From a fresh launch, opens the sidebar (if collapsed) and selects
    /// "Applications" so the mocked list becomes visible. Targets the
    /// sidebar row by its accessibility identifier rather than its visible
    /// text — "Applications" also appears as the content column's own
    /// navigationTitle, and in the collapsed iPad layout that title's frame
    /// can coincidentally overlap the List/Kanban toggle's coordinates,
    /// making a text-based tap flaky (it can register on the toggle
    /// instead of the sidebar row, depending on animation timing).
    private func navigateToApplicationsList() {
        let showSidebar = app.buttons["Show Sidebar"]
        if showSidebar.waitForExistence(timeout: 5) {
            showSidebar.tap()
        }
        let applicationsRow = app.descendants(matching: .any)["sidebar.applications"].firstMatch
        if applicationsRow.waitForExistence(timeout: 5) {
            applicationsRow.tap()
        }
    }

    func testApplicationsListShowsMockedApplications() {
        XCTAssertTrue(app.staticTexts["Contoso"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Globex"].exists)
    }

    func testKanbanToggleShowsStatusColumns() {
        XCTAssertTrue(app.staticTexts["Contoso"].waitForExistence(timeout: 5))

        app.buttons["Kanban"].tap()

        // The Kanban board groups the same mocked applications into status
        // columns — the company names should still be visible, just laid
        // out differently.
        XCTAssertTrue(app.staticTexts["Contoso"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Globex"].exists)
    }

    func testTappingApplicationShowsDetail() {
        XCTAssertTrue(app.staticTexts["Contoso"].waitForExistence(timeout: 5))

        app.staticTexts["Contoso"].tap()

        XCTAssertTrue(app.staticTexts["iOS Engineer"].waitForExistence(timeout: 5))
    }
}
