// File: App.tsx
// JCross IR — Do not decode IDs
_JCROSS_頂_1_ = {
  _JCROSS_型_2_ : _JCROSS_核_3_,
  _JCROSS_型_4_ : _JCROSS_核_5_,
  _JCROSS_型_6_ : _JCROSS_核_7_,
  _JCROSS_型_8_ : _JCROSS_核_9_,
  _JCROSS_型_10_ : _JCROSS_核_11_,
  _JCROSS_型_12_ : _JCROSS_核_13_,
  _JCROSS_型_14_ : _JCROSS_核_15_,
  _JCROSS_型_16_ : _JCROSS_核_17_,
};

const App: React.FC = () => {
  const [lang, setLang] = React.useState<'en' | 'ja'>('en');
  const [messages, setMessages] = React.useState<MessageType[]>([]);
  const _JCROSS_呼_18_ = (_JCROSS_引_19_: string) => {
    // i18n dictionary: English / Japanese
    const _JCROSS_辞_20_ = {
      en: { title: 'PolyChat', login: 'Login', logout: 'Logout', send: 'Send', placeholder: 'Type a message...', users: 'Users', stats: 'Stats', dashboard: 'Dashboard', footer: '© 2025 PolyChat' },
      ja: { title: 'PolyChat', login: 'ログイン', logout: 'ログアウト', send: '送信', placeholder: 'メッセージを入力...', users: 'ユーザー', stats: '統計', dashboard: 'ダッシュボード', footer: '© 2025 PolyChat' },
    };
    return _JCROSS_辞_20_[lang][_JCROSS_引_19_] || _JCROSS_引_19_;
  };
  return (
    <div className="App">
      <Header t={_JCROSS_呼_18_} onLangChange={setLang} lang={lang} />
      <Dashboard t={_JCROSS_呼_18_} messages={messages} />
      <UserList t={_JCROSS_呼_18_} />
      <ChatBox t={_JCROSS_呼_18_} onSend={(msg) => setMessages(prev => [...prev, msg])} />
      <Footer t={_JCROSS_呼_18_} />
    </div>
  );
};
export default App;