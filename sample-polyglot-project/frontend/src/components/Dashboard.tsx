// File: Dashboard.tsx
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
};

const Dashboard: React.FC<{ t: (key: string) => string; messages: { text: string; timestamp: string }[] }> = ({ t, messages }) => {
  const formatLocalTime = (iso: string): string => {
    const date = new Date(iso);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}/${month}/${day} ${hours}:${minutes}`;
  };

  return (
    <div className="dashboard">
      <h2>{t('dashboard')}</h2>
      <ul>
        {messages.map((msg, idx) => (
          <li key={idx}>
            <span className="timestamp">{formatLocalTime(msg.timestamp)}</span>
            <span className="text">{msg.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};
export default Dashboard;