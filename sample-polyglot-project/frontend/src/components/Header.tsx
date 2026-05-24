// File: Header.tsx
// JCross IR — Do not decode IDs
$ENV_SECRET_頂1_ = {
  $ENV_SECRET_型2_ : $ENV_SECRET_核3_,
  $ENV_SECRET_型4_ : {
    $ENV_SECRET_型5_ : $ENV_SECRET_核6_,
    $ENV_SECRET_型7_ : $ENV_SECRET_核8_,
    $ENV_SECRET_型9_ : $ENV_SECRET_核10_,
  },
};

const Header: React.FC<{ t: (key: string) => string; onLangChange: (lang: 'en' | 'ja') => void; lang: 'en' | 'ja' }> = ({ t, onLangChange, lang }) => {
  return (
    <header>
      <h1>{t('title')}</h1>
      <select value={lang} onChange={(e) => onLangChange(e.target.value as 'en' | 'ja')}>
        <option value="en">English</option>
        <option value="ja">日本語</option>
      </select>
      <button>{t('login')}</button>
    </header>
  );
};
export default Header;