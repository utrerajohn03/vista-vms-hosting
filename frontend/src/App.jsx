import Front from './pages/Front.jsx';
import Platform from './pages/Platform.jsx';
import Shell from './pages/Shell.jsx';
import { AppProvider, useApp } from './store.jsx';

function Root() {
  const { S, modal, toastMsg } = useApp();
  return (
    <>
      {S.front ? <Front /> : S.role === 'super' ? <Platform /> : <Shell />}
      {modal}
      <div className="fixed bottom-5 right-5 z-[60]" role="status">
        {toastMsg && <div className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lg">{toastMsg}</div>}
      </div>
    </>
  );
}

export default function App() {
  return <AppProvider><Root /></AppProvider>;
}
