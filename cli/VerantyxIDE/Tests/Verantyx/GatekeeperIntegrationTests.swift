import XCTest
@testable import Verantyx

// MARK: - GatekeeperIntegrationTests
//
// ダミーPaymentServiceモジュールを使ったエンドツーエンドテスト。
// 実際のClaudeは呼び出さず、MockClaudeResponseを使ってパイプライン全体を検証する。

final class GatekeeperIntegrationTests: XCTestCase {

    // MARK: - Fixtures

    /// ダミーPaymentService JCross IR (実ソースの代わり)
    static let dummyPaymentServiceIR = """
    // JCROSS_IR v1.0 — session:TEST_SESSION_001
    // source: PaymentService (anonymized)

    N001 = FUNC_DEF(calculateFee, params:[N002, N003])
    N002 = PARAM(amount: Decimal)
    N003 = PARAM(taxRate: Double)
    N004 = COMPUTE(N002 * N003)
    N005 = RETURN(N004 + N002)
    N006 = FUNC_DEF(validatePayment, params:[N007])
    N007 = PARAM(invoice: Invoice)
    N008 = GUARD(N007.amount > 0)
    N009 = RETURN(true)
    """

    /// Claude が返す正しいフォーマットのモックレスポンス
    static func mockClaudeResponse(realAliases: [String]) -> String {
        guard realAliases.count >= 2 else { return "--- JCROSS_PATCH_BEGIN ---\n// NO_CHANGES_REQUIRED\n--- JCROSS_PATCH_END ---" }
        let a = realAliases[0]
        let b = realAliases[1]
        return """
        --- JCROSS_PATCH_BEGIN ---
        MODIFY_ALIAS \(a):
          // Extract fee computation into intermediate variable
          REPLACE_LINE: N004 = COMPUTE(N002 * N003)
          WITH_LINE:    \(a)_base = COMPUTE(\(a) * \(b))\n          \(a)_result = \(a)_base + \(a)

        MODIFY_ALIAS \(b):
          // Add guard for negative tax rate
          INSERT_AFTER: N003 = PARAM(taxRate: Double)
          INSERT_AFTER: GUARD(\(b) >= 0.0)
        --- JCROSS_PATCH_END ---
        """
    }

    /// Claudeがダミーノードも変更しようとした不正レスポンス
    static func mockClaudeResponseWithDummyAttack(
        realAliases: [String],
        dummyAliases: [String]
    ) -> String {
        let real = realAliases.first ?? "REAL_A"
        let dummy = dummyAliases.first ?? "PHY_0001"
        return """
        --- JCROSS_PATCH_BEGIN ---
        MODIFY_ALIAS \(real):
          REPLACE_LINE: N001 = FUNC_DEF(calculateFee)
          WITH_LINE:    \(real) = OPTIMIZED_FUNC_DEF(calculateFee)

        MODIFY_ALIAS \(dummy):
          REPLACE_LINE: \(dummy) = COMPUTE(gravitationalConstant * orbitalPeriod / CONST_G)
          WITH_LINE:    \(dummy) = OPTIMIZED_GRAVITY_COMPUTE(gravitationalConstant)
        --- JCROSS_PATCH_END ---
        """
    }

    // MARK: - Setup

    var noiseEngine: AdversarialNoiseEngine!
    var validator: JCrossPatchValidator!
    var promptBuilder: ClaudeSystemPromptBuilder!
    var tempVaultURL: URL!

    override func setUp() async throws {
        try await super.setUp()
        noiseEngine   = AdversarialNoiseEngine()
        validator     = JCrossPatchValidator()
        promptBuilder = ClaudeSystemPromptBuilder()
        tempVaultURL  = FileManager.default.temporaryDirectory
            .appendingPathComponent("gatekeeper_test_\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempVaultURL, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: tempVaultURL)
        try await super.tearDown()
    }

    // MARK: - Test 1: フラグメント計画のノイズ率検証

    func testFragmentPlanNoiseRatio() async throws {
        let nodeIDs = ["N001","N002","N003","N004","N005","N006","N007","N008","N009"]

        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_001",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 2,
            maxFragmentsPerSession: 20
        )

        XCTAssertEqual(plan.totalRealCount, nodeIDs.count, "実ノード数が一致するべき")
        XCTAssertGreaterThan(plan.totalDummyCount, 0, "ダミーノードが注入されるべき")
        XCTAssertGreaterThan(plan.noiseRatio, 0.3, "noiseLevel=2でノイズ比は30%超になるべき")
        XCTAssertLessThan(plan.noiseRatio, 0.7, "ノイズ比は70%未満に抑えるべき")

        // IDシャッフルが実施されていることを確認
        for nodeID in nodeIDs {
            let alias = plan.idShuffleMap[nodeID]
            XCTAssertNotNil(alias, "\(nodeID) にエイリアスが割り当てられるべき")
            XCTAssertNotEqual(alias, nodeID, "エイリアスは元のIDと異なるべき")
        }

        // リバースマップが正しいことを確認
        for (nodeID, alias) in plan.idShuffleMap {
            XCTAssertEqual(plan.reverseShuffleMap[alias], nodeID, "逆マップが一致するべき")
        }
    }

    // MARK: - Test 2: ドメイン推測 (金融→軌道力学)

    func testDomainSelectionForFinancialCode() async throws {
        let financialIR = """
        N001 = FUNC_DEF(calculateTax, params:[amount, taxRate])
        N002 = COMPUTE(payment * invoiceRate)
        N003 = RETURN(budget + fee + accountBalance)
        """
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_FINANCE",
            jcrossIR: financialIR,
            nodeIDs: ["N001","N002","N003"],
            noiseLevel: 1
        )
        XCTAssertEqual(plan.selectedDomain, .orbitalMechanics,
                       "金融コードは軌道力学でカモフラージュされるべき")
    }

    // MARK: - Test 3: Claude System Prompt 形式検証

    func testClaudeSystemPromptContainsRequiredMarkers() async throws {
        let nodeIDs = ["N001","N002","N003"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_PROMPT",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 1
        )

        let prompt = promptBuilder.build(
            plan: plan,
            userTask: "Extract fee calculation into a pure function",
            sessionInfo: "TEST_SES_PROMPT"
        )

        // 必須マーカーの存在確認
        XCTAssertTrue(prompt.contains("--- JCROSS_PATCH_BEGIN ---"),
                      "プロンプトにJCROSS_PATCH_BEGINが含まれるべき")
        XCTAssertTrue(prompt.contains("--- JCROSS_PATCH_END ---"),
                      "プロンプトにJCROSS_PATCH_ENDが含まれるべき")
        XCTAssertTrue(prompt.contains("MODIFY_ALIAS"),
                      "プロンプトにMODIFY_ALIASの例が含まれるべき")
        XCTAssertTrue(prompt.contains("[TASK]"),
                      "フラグメントマニフェストに[TASK]ラベルが含まれるべき")
        XCTAssertTrue(prompt.contains("[CONTEXT]") || plan.totalDummyCount == 0,
                      "ダミーがある場合[CONTEXT]ラベルが含まれるべき")

        // バリデーション
        let result = promptBuilder.validatePrompt(prompt)
        XCTAssertTrue(result.isValid, "プロンプトバリデーション失敗: \(result.issues)")
        XCTAssertLessThan(result.estimatedTokens, 4000,
                          "システムプロンプトは4000トークン以内に収めるべき")
    }

    // MARK: - Test 4: 正常パッチのパース・承認

    func testValidPatchAccepted() async throws {
        let nodeIDs = ["N001","N002","N003","N004","N005"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_VALID",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 1
        )

        // RoutingSessionを生成してrealAliasesを取得
        let logger = RoutingSessionLogger(vaultRootURL: tempVaultURL)
        let session = logger.createSession(
            projectID: "test_project",
            sourceRelativePath: "PaymentService",
            schemaSessionID: "TEST_SCHEMA_001",
            camouflageDomain: .orbitalMechanics
        )

        // フラグメントを登録
        for fragment in plan.fragments {
            if fragment.kind == .real {
                logger.addRealFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                       claudeAlias: fragment.claudeAlias, role: fragment.role)
            } else {
                logger.addDummyFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                        claudeAlias: fragment.claudeAlias, domain: fragment.domain ?? .orbitalMechanics)
            }
        }

        guard let updatedSession = logger.session(id: session.sessionID) else {
            XCTFail("セッションが見つかりません"); return
        }

        let realAliases = Array(updatedSession.realNodeAliases)
        let mockResponse = Self.mockClaudeResponse(realAliases: realAliases)

        let patches = validator.parsePatches(from: mockResponse, session: updatedSession)
        XCTAssertFalse(patches.isEmpty, "パッチがパースされるべき")

        let summary = validator.validate(patches: patches, session: updatedSession)
        XCTAssertFalse(summary.acceptedPatches.isEmpty, "正常パッチは承認されるべき")
        XCTAssertEqual(summary.dummyPatchCount, 0, "ダミーパッチはないはず")
        XCTAssertEqual(summary.hallucinatedPatchCount, 0, "Hallucinated aliasはないはず")
        XCTAssertGreaterThan(summary.acceptanceRate, 0.5, "承認率は50%超であるべき")
    }

    // MARK: - Test 5: ダミーパッチが廃棄されること

    func testDummyPatchesAreFiltered() async throws {
        let nodeIDs = ["N001","N002","N003"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_FILTER",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 2
        )

        let logger = RoutingSessionLogger(vaultRootURL: tempVaultURL)
        let session = logger.createSession(
            projectID: "test_project",
            sourceRelativePath: "PaymentService",
            schemaSessionID: "TEST_SCHEMA_002",
            camouflageDomain: .orbitalMechanics
        )

        for fragment in plan.fragments {
            if fragment.kind == .real {
                logger.addRealFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                       claudeAlias: fragment.claudeAlias, role: fragment.role)
            } else {
                logger.addDummyFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                        claudeAlias: fragment.claudeAlias, domain: fragment.domain ?? .orbitalMechanics)
            }
        }

        guard let updatedSession = logger.session(id: session.sessionID) else {
            XCTFail("セッションが見つかりません"); return
        }

        let realAliases = Array(updatedSession.realNodeAliases)
        let dummyAliases = Array(updatedSession.dummyNodeAliases)

        guard !dummyAliases.isEmpty else {
            // noiseLevel=2でダミーが生成されなければスキップ
            return
        }

        let mockResponse = Self.mockClaudeResponseWithDummyAttack(
            realAliases: realAliases,
            dummyAliases: dummyAliases
        )

        let patches = validator.parsePatches(from: mockResponse, session: updatedSession)
        let summary = validator.validate(patches: patches, session: updatedSession)

        XCTAssertGreaterThan(summary.dummyPatchCount, 0,
                             "ダミーノードへのパッチが検出されるべき")
        XCTAssertEqual(
            summary.acceptedPatches.filter { dummyAliases.contains($0.targetAlias) }.count,
            0,
            "ダミーノードへのパッチは承認されるべきではない"
        )
    }

    // MARK: - Test 6: フォーマット違反レスポンスが全件廃棄されること

    func testMalformedResponseProducesNoPatches() async throws {
        let nodeIDs = ["N001","N002"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_MALFORM",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 1
        )

        let logger = RoutingSessionLogger(vaultRootURL: tempVaultURL)
        let session = logger.createSession(
            projectID: "test_project",
            sourceRelativePath: "PaymentService",
            schemaSessionID: "TEST_SCHEMA_003",
            camouflageDomain: .orbitalMechanics
        )

        for fragment in plan.fragments where fragment.kind == .real {
            logger.addRealFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                   claudeAlias: fragment.claudeAlias, role: fragment.role)
        }

        guard let updatedSession = logger.session(id: session.sessionID) else {
            XCTFail("セッションが見つかりません"); return
        }

        // フォーマット違反: マーカーなしの自然言語レスポンス
        let malformedResponses = [
            "Sure! I'll refactor the calculateFee function to extract...",
            "```swift\nfunc calculateFee(amount: Decimal, taxRate: Double) { ... }\n```",
            "MODIFY_ALIAS XX999:\n  REPLACE_LINE: foo\n  WITH_LINE: bar",  // マーカーなし
            "",
            "   \n\n   ",
        ]

        for malformed in malformedResponses {
            let patches = validator.parsePatches(from: malformed, session: updatedSession)
            let summary = validator.validate(patches: patches, session: updatedSession)
            XCTAssertEqual(summary.acceptedPatches.count, 0,
                           "フォーマット違反レスポンスはパッチを生成すべきでない: \(malformed.prefix(40))")
        }
    }

    // MARK: - Test 7: リバースシャッフルマップの正確性

    func testReverseShuffleMapAccuracy() async throws {
        let nodeIDs = ["N001","N002","N003","N004","N005"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_REVERSE",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 0  // ノイズなしで純粋にID変換のみテスト
        )

        for nodeID in nodeIDs {
            guard let alias = plan.idShuffleMap[nodeID] else {
                XCTFail("\(nodeID)のエイリアスが存在しない"); continue
            }
            let recovered = plan.reverseShuffleMap[alias]
            XCTAssertEqual(recovered, nodeID,
                           "逆変換: alias(\(alias)) → \(nodeID) が正確であるべき")
        }
    }

    // MARK: - Test 8: 全フォーマットチェック (NO_CHANGES_REQUIREDを含む)

    func testNoChangesRequiredResponseIsAccepted() async throws {
        let nodeIDs = ["N001"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_NOCHANGE",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 0
        )

        let logger = RoutingSessionLogger(vaultRootURL: tempVaultURL)
        let session = logger.createSession(
            projectID: "test_project",
            sourceRelativePath: "PaymentService",
            schemaSessionID: "TEST_SCHEMA_004",
            camouflageDomain: .orbitalMechanics
        )
        for fragment in plan.fragments where fragment.kind == .real {
            logger.addRealFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                   claudeAlias: fragment.claudeAlias, role: fragment.role)
        }

        guard let updatedSession = logger.session(id: session.sessionID) else {
            XCTFail("セッションが見つかりません"); return
        }

        let noChangeResponse = """
        --- JCROSS_PATCH_BEGIN ---
        // NO_CHANGES_REQUIRED
        --- JCROSS_PATCH_END ---
        """

        // パース時にエラーにならないことを確認
        let patches = validator.parsePatches(from: noChangeResponse, session: updatedSession)
        // NO_CHANGES は空パッチとして処理される (エラーではない)
        XCTAssertEqual(patches.count, 0, "NO_CHANGES_REQUIREDは空のパッチリストを返すべき")

        let summary = validator.validate(patches: patches, session: updatedSession)
        XCTAssertEqual(summary.totalPatches, 0)
        XCTAssertFalse(summary.hasHallucinations)
    }

    // MARK: - Test 9: Bonsai-8B プロンプト生成

    func testBonsaiValidationPromptGenerated() async throws {
        let nodeIDs = ["N001","N002","N003"]
        let plan = await noiseEngine.planFragmentation(
            sessionID: "TEST_SES_BONSAI",
            jcrossIR: Self.dummyPaymentServiceIR,
            nodeIDs: nodeIDs,
            noiseLevel: 1
        )

        let logger = RoutingSessionLogger(vaultRootURL: tempVaultURL)
        let session = logger.createSession(
            projectID: "test_project",
            sourceRelativePath: "PaymentService",
            schemaSessionID: "TEST_SCHEMA_005",
            camouflageDomain: .orbitalMechanics
        )
        for fragment in plan.fragments where fragment.kind == .real {
            logger.addRealFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                   claudeAlias: fragment.claudeAlias, role: fragment.role)
        }

        guard let updatedSession = logger.session(id: session.sessionID) else {
            XCTFail("セッションが見つかりません"); return
        }

        let realAliases = Array(updatedSession.realNodeAliases)
        let mockResponse = Self.mockClaudeResponse(realAliases: realAliases)
        let patches = validator.parsePatches(from: mockResponse, session: updatedSession)
        let summary = validator.validate(patches: patches, session: updatedSession)

        let bonsaiPrompt = validator.buildBonsaiValidationPrompt(
            summary: summary,
            session: updatedSession
        )

        XCTAssertTrue(bonsaiPrompt.contains("YES") || bonsaiPrompt.contains("NO"),
                      "Bonsaiプロンプトには YES/NO の判定指示が含まれるべき")
        XCTAssertFalse(bonsaiPrompt.isEmpty, "Bonsaiプロンプトが空であってはならない")
        XCTAssertLessThan(bonsaiPrompt.count / 4, 800,
                          "Bonsai-8Bのコンテキスト予算を考慮し800トークン以内であるべき")
    }

    // MARK: - Test 10: 完全なE2E統合フロー (MockClaudeで通し確認)

    func testFullE2EPipelineWithMockClaude() async throws {
        let nodeIDs = ["N001","N002","N003","N004","N005","N006"]
        let jcrossIR = Self.dummyPaymentServiceIR

        // Step 1: フラグメント計画
        let plan = await noiseEngine.planFragmentation(
            sessionID: "E2E_TEST_001",
            jcrossIR: jcrossIR,
            nodeIDs: nodeIDs,
            noiseLevel: 2
        )
        XCTAssertFalse(plan.fragments.isEmpty)

        // Step 2: プロンプト生成
        let prompt = promptBuilder.build(
            plan: plan,
            userTask: "Add input validation guards to all functions",
            sessionInfo: "E2E_TEST_001"
        )
        let validation = promptBuilder.validatePrompt(prompt)
        XCTAssertTrue(validation.isValid, "プロンプトが有効でないといけない: \(validation.issues)")

        // Step 3: セッション登録
        let logger = RoutingSessionLogger(vaultRootURL: tempVaultURL)
        let session = logger.createSession(
            projectID: "e2e_test",
            sourceRelativePath: "PaymentService",
            schemaSessionID: "E2E_SCHEMA_001",
            camouflageDomain: plan.selectedDomain
        )
        for fragment in plan.fragments {
            if fragment.kind == .real {
                logger.addRealFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                       claudeAlias: fragment.claudeAlias, role: fragment.role)
            } else {
                logger.addDummyFragment(to: session.sessionID, nodeID: fragment.nodeID,
                                        claudeAlias: fragment.claudeAlias,
                                        domain: fragment.domain ?? .orbitalMechanics)
            }
        }

        guard let updatedSession = logger.session(id: session.sessionID) else {
            XCTFail("セッションが見つかりません"); return
        }

        // Step 4: MockClaudeレスポンス (正常 + ダミー攻撃を含む)
        let realAliases = Array(updatedSession.realNodeAliases)
        let dummyAliases = Array(updatedSession.dummyNodeAliases)
        let mockResponse = Self.mockClaudeResponseWithDummyAttack(
            realAliases: realAliases,
            dummyAliases: dummyAliases
        )

        // Step 5: パッチパース
        let patches = validator.parsePatches(from: mockResponse, session: updatedSession)

        // Step 6: バリデーション (ダミーはフィルタされるべき)
        let summary = validator.validate(patches: patches, session: updatedSession)

        if !dummyAliases.isEmpty {
            XCTAssertGreaterThan(summary.dummyPatchCount, 0,
                                 "ダミーパッチが検出されるべき")
        }

        // Step 7: 逆変換マップの適用
        let resolved = validator.applyReverseShuffleMap(
            to: summary,
            reverseMap: plan.reverseShuffleMap
        )

        // 全解決済みパッチのnodeIDは元のノードIDセットに含まれるべき
        for (nodeID, _) in resolved {
            XCTAssertTrue(
                nodeIDs.contains(nodeID) || nodeID.hasPrefix("DUMMY_"),
                "解決されたnodeID '\(nodeID)' は元のノードセットに含まれるべき"
            )
        }

        // Step 8: 統計確認
        XCTAssertEqual(summary.totalPatches, patches.count,
                       "summary.totalPatches がパース結果と一致するべき")

        print("""

        ═══════════════════════════════════════
          E2E Integration Test Results
        ═══════════════════════════════════════
        Domain selected  : \(plan.selectedDomain.rawValue)
        Fragments sent   : \(plan.fragments.count) (\(plan.totalRealCount) real, \(plan.totalDummyCount) dummy)
        Noise ratio      : \(String(format: "%.0f", plan.noiseRatio * 100))%
        Patches received : \(summary.totalPatches)
        Accepted         : \(summary.acceptedPatches.count)
        Dummy blocked    : \(summary.dummyPatchCount)
        Hallucinated     : \(summary.hallucinatedPatchCount)
        Resolved to nodeID: \(resolved.count)
        Prompt tokens    : ~\(validation.estimatedTokens)
        ═══════════════════════════════════════
        """)
    }
}
