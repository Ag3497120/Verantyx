// File: StatCard.tsx
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
};

const StatCard: React.FC<{ t: (key: string) => string; label: string; value: number }> = ({ t, label, value }) => {
  return (
    <div className="statcard">
      <span className="label">{t(label)}</span>
      <span className="value">{value}</span>
    </div>
  );
};
export default StatCard;