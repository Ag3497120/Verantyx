// File: UserList.tsx
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
};

const UserList: React.FC<{ t: (key: string) => string }> = ({ t }) => {
  return (
    <div className="userlist">
      <h2>{t('users')}</h2>
      <ul>
        <li>Alice</li>
        <li>Bob</li>
        <li>Charlie</li>
      </ul>
    </div>
  );
};
export default UserList;