// File: api.ts
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
};

export function sendMessage(text: string) {
  const _JCROSS_utc_ts_8_ = new Date().toISOString();
  return fetch("/api/messages", {
    method: "POST",
    body: JSON.stringify({ text, timestamp: _JCROSS_utc_ts_8_ }),
    headers: { "Content-Type": "application/json" },
  });
}