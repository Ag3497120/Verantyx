function renderInputRules() {
  const el = document.getElementById("inputRules");
  if (!el) return;
  el.innerHTML = `
    <b>入力ルール（常時表示）</b><br/>
    ・式（論理式/数式）は <b>ダブルクォーテーション "..."</b> で囲ってください<br/>
    ・様相論理： "[]p -> [][]p" / "box p -> box box p" のどちらでもOK<br/>
    ・命題論理： "((A -> B) & A) -> B" のように (&, |, ~, ->) を使用<br/>
    ・選択肢： A. "..." B. "..." の形式が使えます
  `;
}
window.renderInputRules = renderInputRules;
