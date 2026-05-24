// File: Footer.tsx
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
};

const Footer: React.FC<{ t: (key: string) => string }> = ({ t }) => {
  return (
    <footer>
      <p>{t('footer')}</p>
    </footer>
  );
};
export default Footer;