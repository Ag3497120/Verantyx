// File: ChatBox.tsx
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
  _JCROSS_型_8_ : _JCROSS_核_9_,
  _JCROSS_型_10_ : _JCROSS_核_11_,
};

const ChatBox: React.FC<{ t: (key: string) => string; onSend: (msg: { text: string; timestamp: string }) => void }> = ({ t, onSend }) => {
  const [input, setInput] = React.useState('');

  const formatTimestamp = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}/${month}/${day} ${hours}:${minutes}`;
  };

  const handleSend = () => {
    if (input.trim() === '') return;
    const _JCROSS_日付_12_ = new Date();
    // Note: Date in browser is local time; we convert to UTC for backend.
    const _JCROSS_utc_13_ = new Date(_JCROSS_日付_12_.getTime() + _JCROSS_日付_12_.getTimezoneOffset() * 60000);
    onSend({ text: input, timestamp: _JCROSS_utc_13_.toISOString() });
    setInput('');
  };

  return (
    <div className="chatbox">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={t('placeholder')}
      />
      <button onClick={handleSend}>{t('send')}</button>
    </div>
  );
};
export default ChatBox;