import Foundation

/// 視覚モデルに渡す文面。**これは文章ではなく設定です。**
///
/// 事前登録: `engine/experiments/garment_vision/PREREG3_PROMPT.md`
///
/// 実測(2026-08-22, Qwen3.6-35B-A3B, 温度0.0, 正解が確定した合成線画):
/// 同じモデル・同じコマ・同じ温度で、文面の些細な差によって、
/// 単色の線画から生地を**4回とも断言**したり、**6回とも飛ばして
/// 観測項目を12/12で当てたり**した。差は一文の位置と、
/// 「他の文章は不要です」の有無だけだった。
///
/// つまり捏造はモデルの能力ではなく設定である。**測らずに書き換えない。**
/// 変えるなら `experiments/garment_vision/run_prompt_ablate.py` を回し、
/// `measured` を更新すること。ここを気軽に直すと、9倍速いモデルが
/// 静かに嘘を書き始める。
enum AtelierPrompts {

    /// ひとつの文面と、それを支える実測。
    struct Measured {
        /// 文面そのもの。
        let text: String
        /// いつ、何で測ったか。
        let evidence: String
        /// 測ったモデル。他のモデルでは測っていない。
        let measuredOn: String
    }

    /// コマ一枚を読ませる文面。
    ///
    /// **側面の一覧は呼び手が差し込む。** 空いている側面だけを訊くのが
    /// この画面の仕事で、全側面を毎回訊くと、既に確定したものについて
    /// モデルの意見が並ぶ。
    static func readFrame(openAspects: [String]) -> Measured {
        let list = openAspects.isEmpty
            ? "(全側面)" : openAspects.joined(separator: "\n")
        return Measured(
            text: """
            これは一着の服が映った一枚です。**この一枚で実際に見えているもの**
            だけを答えてください。見えないものは飛ばしてください。推測で埋めないで
            ください。

            対象の側面:
            \(list)
            あなたの出力は提案として記録され、人が採用するまで設計図には入りません。

            JSON 配列だけを返してください:
            [{"part":"collar","aspect":"shape","value":"ノッチドラペル","why":"襟の返りが見える"}]
            """,
            evidence: "生地の断言 0/6、観測できるもの 12/12 "
                + "(合成線画3コマ×2回、温度0.0、思考オフ)",
            measuredOn: "qwen/qwen3.6-35b-a3b @ 2026-08-22")
    }

    /// 空いている側面について、絵を見ずに心当たりを訊く文面。
    ///
    /// **こちらはまだ測っていない。** 絵が無い分だけ捏造が出やすいはずで、
    /// 同じ扱いにしてはいけない。測るまでは「未測定」と明示する。
    static func askOpenAspects(known: String,
                               open: [String]) -> Measured {
        Measured(
            text: """
            あなたは服飾の解析をしています。以下は、ある一着について
            **今わかっていること**と、**まだ観測できていない側面**です。

            わかっていること:
            \(known.isEmpty ? "(まだ何もありません)" : known)

            観測できていない側面:
            \(open.joined(separator: "\n"))

            それぞれについて、心当たりがあれば候補を挙げてください。
            断定はしないでください。わからないものは飛ばしてください。
            憶測で埋めないでください。

            JSON 配列だけを返してください:
            [{"part":"collar","aspect":"material","value":"ウール","why":"根拠"}]
            """,
            evidence: "未測定。絵を見ない分だけ捏造が出やすいはずだが、"
                + "確かめていない",
            measuredOn: "—")
    }
}
