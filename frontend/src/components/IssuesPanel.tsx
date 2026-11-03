// UIK-6 Панель результатов проверки: группы Block / Warn / Escalate / Auto-fix / Info, переход к полю (вкладке)
import { observer } from 'mobx-react-lite';
import { app } from '../store';

const GROUPS: [string, string, string][] = [
  ['Block', 'Block — критические ошибки (L1 / XSD)', 'banner-err'], ['Escalate', 'Escalate — требуется решение ответственного', 'banner-warn'],
  ['Warn', 'Warn — предупреждения (L2)', 'banner-warn'], ['Auto-fix', 'Auto-fix — исправлено автоматически', 'banner-info'], ['Info', 'Info — подсказки (L3, L5)', 'banner-info'],
];

const IssuesPanel = observer(({ issues, onGo }: { issues: any[]; onGo?: (tab: string) => void }) => {
  if (!issues?.length) return <div className="banner-ok">Замечаний по правилам модели v3.8 нет.</div>;
  return (
    <div>
      {GROUPS.map(([act, title, cls]) => {
        const items = issues.filter((i) => i.action === act);
        if (!items.length) return null;
        return (
          <div key={act} className={cls}>
            <b>{title}: {items.length}</b>
            {items.map((i, k) => (
              <div key={k} style={{ background: 'rgba(255,255,255,.9)', color: '#1B1F24', padding: '6px 10px', borderRadius: 6, marginTop: 6, display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                <span>{app.techMode && <b className="mono" style={{ color: '#1F5FAD', marginRight: 6 }}>[{i.id}]</b>}<span title={i.id}>{i.text}</span></span>
                {onGo && i.tab && <a style={{ whiteSpace: 'nowrap' }} onClick={() => onGo(i.tab)}>К полю ({i.tab}) →</a>}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
});

export default IssuesPanel;
