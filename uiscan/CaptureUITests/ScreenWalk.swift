//
//  ScreenWalk.swift
//  uiscan
//
//  A resilient walk through every screen of ExposurePal.
//
//  Design rules, learned the hard way:
//   * Never assert your way out of a route. A hard failure halfway through
//     leaves a half-empty contact sheet, which is worse than a screenshot of a
//     screen that did not open — at least that one shows you what went wrong.
//   * Prefer accessibility identifiers, fall back to labels, fall back to
//     normalised coordinates. UI drifts; a screenshot tool should survive it.
//   * Every route relaunches, so routes never inherit each other's state.
//

import XCTest

final class ScreenWalk: XCTestCase {

    private let bundleID = "com.zorrobyte.ExposurePal"

    override func setUp() {
        super.setUp()
        // Keep walking after a missing element so one drifted label cannot
        // wipe out the rest of the sheet.
        continueAfterFailure = true
        executionTimeAllowance = 240
    }

    // MARK: - Harness

    /// Launch onboarded and seeded unless a route wants the true first run.
    private func launch(fresh: Bool = false) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: bundleID)
        app.launchArguments = fresh ? [] : ["-uiscan-onboarded", "-uiscan-seed"]
        app.launch()
        _ = app.wait(for: .runningForeground, timeout: 20)
        return app
    }

    private func snap(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// First hittable match for an identifier or a label, or nil.
    private func element(_ app: XCUIApplication, _ key: String) -> XCUIElement? {
        let byID = app.descendants(matching: .any).matching(identifier: key).firstMatch
        if byID.exists { return byID }
        for kind in [app.buttons, app.staticTexts, app.cells, app.otherElements, app.switches] {
            let match = kind[key]
            if match.exists { return match }
        }
        let fuzzy = app.buttons.containing(NSPredicate(format: "label CONTAINS[c] %@", key)).firstMatch
        return fuzzy.exists ? fuzzy : nil
    }

    @discardableResult
    private func tap(_ app: XCUIApplication, _ key: String, settle: UInt32 = 2) -> Bool {
        guard let target = element(app, key) else { return false }
        if target.isHittable {
            target.tap()
        } else {
            target.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
        sleep(settle)
        return true
    }

    private func tapTab(_ app: XCUIApplication, _ identifier: String, fallbackX: CGFloat) {
        if !tap(app, identifier) {
            app.coordinate(withNormalizedOffset: CGVector(dx: fallbackX, dy: 0.965)).tap()
            sleep(2)
        }
    }

    /// Screenshot the top of a scroll view, then each further screenful.
    private func snapScrolling(_ app: XCUIApplication, _ stem: String, pages: Int) {
        snap(app, "\(stem)")
        for page in 1..<max(pages, 1) {
            app.swipeUp()
            sleep(1)
            snap(app, "\(stem)-\(page)")
        }
    }

    private func back(_ app: XCUIApplication) {
        if !tap(app, "BackButton", settle: 1) {
            app.navigationBars.buttons.firstMatch.tap()
            sleep(1)
        }
    }

    private func dismissSheet(_ app: XCUIApplication) {
        for key in ["Close", "Done", "Cancel"] {
            if tap(app, key, settle: 1) { return }
        }
        app.swipeDown()
        sleep(1)
    }

    // MARK: - Routes

    func test01Onboarding() {
        let app = launch(fresh: true)
        for page in 1...6 {
            snap(app, String(format: "%02d-onboarding-%d", page, page))
            if !tap(app, "continue_button", settle: 1) {
                _ = tap(app, "lets_go_button", settle: 2)
                break
            }
        }
        snap(app, "07-onboarding-finished")
    }

    func test02EmptyStates() {
        // Onboarded but never seeded: what a real day-one user actually sees.
        // Must run before any seeding route — the container is shared per device.
        let app = XCUIApplication(bundleIdentifier: bundleID)
        app.launchArguments = ["-uiscan-onboarded"]
        app.launch()
        _ = app.wait(for: .runningForeground, timeout: 20)
        tapTab(app, "tab_home", fallbackX: 0.1)
        sleep(5)
        snap(app, "08-empty-home")
        tapTab(app, "tab_journal", fallbackX: 0.5)
        sleep(2)
        snap(app, "09-empty-collection")
    }

    func test03Home() {
        let app = launch()
        tapTab(app, "tab_home", fallbackX: 0.1)
        sleep(4)  // Home deals a mission card once a location fix lands.
        snapScrolling(app, "10-home", pages: 3)
        if tap(app, "open_world_map") {
            snap(app, "13-home-world-map")
            dismissSheet(app)
        }
    }

    func test04Explore() {
        let app = launch()
        tapTab(app, "tab_explore", fallbackX: 0.3)
        sleep(8)  // MapKit search has to come back before this screen means anything.
        snapScrolling(app, "20-explore", pages: 3)
        if tap(app, "Filter places") {
            snap(app, "23-explore-filters")
            dismissSheet(app)
        }
    }

    func test05MissionDetail() {
        let app = launch()
        tapTab(app, "tab_home", fallbackX: 0.1)
        sleep(8)
        let card = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH %@", "mission_card_")).firstMatch
        if card.waitForExistence(timeout: 30) {
            card.tap()
            sleep(3)
            snapScrolling(app, "30-mission-detail", pages: 2)
        } else {
            snap(app, "30-mission-detail-unavailable")
        }
    }

    func test06ActiveMission() {
        let app = launch()
        tapTab(app, "tab_home", fallbackX: 0.1)
        sleep(8)
        let card = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH %@", "mission_card_")).firstMatch
        guard card.waitForExistence(timeout: 30) else {
            snap(app, "40-active-unavailable")
            return
        }
        card.tap()
        sleep(2)
        for key in ["Let's Go", "Start", "navigate_button"] {
            if tap(app, key, settle: 4) { break }
        }
        snapScrolling(app, "40-active-transit", pages: 2)
        if tap(app, "im_here_button", settle: 3) {
            snapScrolling(app, "42-active-onsite", pages: 3)
            if tap(app, "complete_mission_button", settle: 3) {
                snapScrolling(app, "45-completion", pages: 3)
            }
        }
    }

    func test07Collection() {
        let app = launch()
        tapTab(app, "tab_journal", fallbackX: 0.5)
        sleep(3)
        snapScrolling(app, "50-collection", pages: 2)
        for mode in ["Map", "Grid", "List", "Outings"] {
            if tap(app, mode) { snap(app, "52-collection-\(mode.lowercased())") }
        }
        tapTab(app, "tab_journal", fallbackX: 0.5)
        if tap(app, "Demo · City Gallery") {
            snapScrolling(app, "55-place-detail", pages: 4)
        }
    }

    func test08Support() {
        let app = launch()
        tapTab(app, "tab_learn", fallbackX: 0.7)
        sleep(2)
        snap(app, "60-support")
        let tools = ["Breathing", "Grounding", "Butterfly Hug", "Cold Technique",
                     "Affirmations", "Muscle Relaxation"]
        for (index, tool) in tools.enumerated() {
            guard tap(app, tool, settle: 3) else { continue }
            snap(app, String(format: "6%d-support-%@", index + 1, tool.replacingOccurrences(of: " ", with: "-").lowercased()))
            back(app)
        }
    }

    func test09Audio() {
        let app = launch()
        tapTab(app, "tab_learn", fallbackX: 0.7)
        guard tap(app, "Listen", settle: 3) else {
            snap(app, "70-audio-unavailable")
            return
        }
        snapScrolling(app, "70-audio-library", pages: 2)
        for (index, category) in ["Guided Meditations", "Soundscapes", "My Audio"].enumerated() {
            guard tap(app, category, settle: 2) else { continue }
            snap(app, "7\(index + 2)-audio-\(index)")
            back(app)
        }
    }

    func test10Me() {
        let app = launch()
        tapTab(app, "tab_me", fallbackX: 0.9)
        sleep(2)
        snapScrolling(app, "80-me", pages: 3)
        for (index, row) in ["Reminders", "Remember my outings"].enumerated() {
            guard tap(app, row, settle: 2) else { continue }
            snap(app, "8\(index + 4)-me-\(row.replacingOccurrences(of: " ", with: "-").lowercased())")
            back(app)
        }
    }

    func test11CreateMission() {
        let app = launch()
        tapTab(app, "tab_explore", fallbackX: 0.3)
        sleep(4)
        // Each of these is a step, not an alternative — walk as far as the UI allows.
        for key in ["Mission actions", "Saved missions", "New mission",
                    "my_missions_create_a_mission", "Create a mission"] {
            _ = tap(app, key, settle: 2)
        }
        snapScrolling(app, "90-create-mission", pages: 2)
    }

}
