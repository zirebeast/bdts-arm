import { useLocation, useNavigate } from 'react-router-dom';

const STEPS: [string, string, string, string][] = [
  ['1', 'Загрузка пообъектного плана', 'ФМ-5.1 «Формирование планов» → БДТС', '/inbound/plan'],
  ['2', 'Список объектов X/Y/Z', 'Строки ПП → объекты диагностирования', '/inbound/objects'],
  ['3', 'ЕО объекта из БДО', 'МП-3 «БДО» (ФМ-3.2) → БДТС; создать / скопировать ЕО', '/inbound/objects/'],
];

export default function FlowBar() {
  const loc = useLocation();
  const nav = useNavigate();
  const cur = loc.pathname.startsWith('/inbound/objects/') ? 2 : loc.pathname.startsWith('/inbound/objects') ? 1 : 0;
  return (
    <ol className="grid g3" style={{ listStyle: 'none', padding: 0, margin: '0 0 12px' }} aria-label="Сценарий входящих интеграций">
      {STEPS.map(([n, t, sub, to], i) => (
        <li key={n}>
          <button className="kpi" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', background: cur === i ? '#E3EEFB' : undefined, borderColor: cur === i ? '#1F5FAD' : undefined }}
            onClick={() => i < 2 && nav(to)} aria-current={cur === i ? 'step' : undefined}>
            <span style={{ width: 24, height: 24, borderRadius: 12, background: cur === i ? '#1F5FAD' : '#EEF1F4', color: cur === i ? '#fff' : '#5A6472', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, flexShrink: 0 }}>{n}</span>
            <span><b>{t}</b><div className="hint">{sub}</div></span>
          </button>
        </li>
      ))}
    </ol>
  );
}
