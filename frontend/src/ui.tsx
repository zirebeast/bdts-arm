// Общие компоненты UI-kit (UIK-1…UIK-11): статусные чипы, заголовки, история, решения, файлы, допуски
import {
  AlertOutlined, CheckCircleOutlined, CheckOutlined, ClockCircleOutlined, CloseCircleOutlined, DeleteOutlined, EditOutlined,
  ExclamationCircleOutlined, EyeOutlined, FileTextOutlined, InfoCircleOutlined, SafetyOutlined, SendOutlined, SyncOutlined, ToolOutlined, UploadOutlined, WarningOutlined,
} from '@ant-design/icons';
import { Button, Card, Empty, Input, Modal, Result, Segmented, Space, Table, Tag, Tooltip, Typography, Upload, message } from 'antd';
import dayjs from 'dayjs';
import { observer } from 'mobx-react-lite';
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, errText, uploadFile } from './api';
import { app } from './store';

export const C = {
  primary: '#1F5FAD', text: '#1B1F24', sec: '#5A6472', border: '#D5DAE1', page: '#F4F6F8', surface: '#FFFFFF',
  levels: {
    neutral: { fg: '#5F6B7A', bg: '#EEF1F4', bd: '#D5DAE1' },
    progress: { fg: '#1565C0', bg: '#E3EEFB', bd: '#B6D4F7' },
    action: { fg: '#B54708', bg: '#FEF0E1', bd: '#FAD6B0' },
    done: { fg: '#1E7B34', bg: '#E5F4E8', bd: '#B7E1C0' },
    error: { fg: '#B42318', bg: '#FDECEA', bd: '#F8C5C0' },
  },
};

type Level = keyof typeof C.levels;
const S = (level: Level, icon: React.ReactNode) => ({ level, icon });
// Пятиуровневая шкала статусов (ТЗ, раздел 5): статус не передаётся только цветом — у чипа есть текст и иконка
const STATUS: Record<string, { level: Level; icon: React.ReactNode }> = {
  'Черновик': S('neutral', <EditOutlined />), 'Помечено на удаление': S('neutral', <DeleteOutlined />), 'Метод не проводился': S('neutral', <CloseCircleOutlined />),
  'Не начато': S('neutral', <ClockCircleOutlined />), 'Не начат': S('neutral', <ClockCircleOutlined />), 'Не заполнено': S('neutral', <ClockCircleOutlined />),
  'На согласовании': S('progress', <ClockCircleOutlined />), 'ПЭ не завершен': S('progress', <ToolOutlined />), 'На рассмотрении ДЭО': S('progress', <EyeOutlined />),
  'На согласовании в ДЭО': S('progress', <EyeOutlined />), 'Отправлено на экспертизу': S('progress', <SafetyOutlined />), 'Направлено в Ростехнадзор': S('progress', <SendOutlined />),
  'Загружен': S('progress', <UploadOutlined />), 'Полевой этап завершен': S('progress', <CheckOutlined />), 'Технический отчет сформирован': S('progress', <FileTextOutlined />),
  'В работе': S('progress', <SyncOutlined />), 'Проверка': S('progress', <SyncOutlined />), 'Направлен в ГД': S('progress', <SendOutlined />), 'Заполнен': S('progress', <CheckOutlined />),
  'Согласовано': S('done', <CheckCircleOutlined />), 'Принят ДЭО': S('done', <CheckCircleOutlined />), 'Результат получен': S('done', <CheckCircleOutlined />),
  'Выполнено': S('done', <CheckCircleOutlined />), 'Подтверждено': S('done', <CheckCircleOutlined />), 'Завершено ДЭО': S('done', <CheckCircleOutlined />),
  'Согласовано Ростехнадзором, завершено': S('done', <CheckCircleOutlined />), 'Действует': S('done', <CheckCircleOutlined />), 'Успешно': S('done', <CheckCircleOutlined />),
  'Завершено': S('done', <CheckCircleOutlined />), 'Синхронизирована': S('done', <SyncOutlined />), 'Проведён': S('done', <CheckCircleOutlined />), 'Принят': S('done', <CheckCircleOutlined />),
  'Опубликован': S('done', <CheckCircleOutlined />), 'Всё введено': S('done', <CheckCircleOutlined />), 'Завершён': S('done', <CheckCircleOutlined />),
  'На корректировке': S('action', <ExclamationCircleOutlined />), 'Требуется КП': S('action', <EditOutlined />), 'Требуется ЭПБ': S('action', <SafetyOutlined />),
  'Требует подтверждения': S('action', <AlertOutlined />), 'На доработке': S('action', <EditOutlined />), 'С предупреждениями': S('action', <WarningOutlined />),
  'Есть предупреждения': S('action', <WarningOutlined />), 'Ожидает добавления в БДО': S('action', <ClockCircleOutlined />), 'Открыт': S('action', <ExclamationCircleOutlined />),
  'Допустимо с ремонтом': S('action', <ToolOutlined />),
  'Ошибка проверки': S('error', <CloseCircleOutlined />), 'Ошибка': S('error', <CloseCircleOutlined />), 'Просрочен': S('error', <CloseCircleOutlined />),
  'Отклонено': S('error', <CloseCircleOutlined />), 'Конфликт с БДО': S('error', <WarningOutlined />),
};

export function StatusChip({ status, compact }: { status?: string; compact?: boolean }) {
  if (!status) return <span style={{ color: C.sec }}>—</span>;
  const cfg = STATUS[status] || S('neutral', <InfoCircleOutlined />);
  const l = C.levels[cfg.level];
  return (
    <span className="chip" style={{ color: l.fg, background: l.bg, borderColor: l.bd, padding: compact ? '0 6px' : '1px 8px' }}>
      {cfg.icon}
      <span>{status}</span>
    </span>
  );
}

export const fmtDate = (s?: string | null) => (s ? dayjs(s).format('DD.MM.YYYY') : '—');
export const fmtDateTime = (s?: string | null) => (s ? dayjs(s).format('DD.MM.YYYY HH:mm') : '—');
export const fmtNum = (v: any, d = 2) => (v === null || v === undefined || v === '' ? '—' : Number(v).toLocaleString('ru-RU', { maximumFractionDigits: d }));

/** Код правила/экрана: виден в «режиме кодов», иначе — только в подсказке. */
export const Rule = observer(({ code, text }: { code?: string; text?: string }) => {
  if (!code) return null;
  return app.techMode ? <Tag className="mono" color="gold" style={{ marginInline: 4 }} title={text}>{code}</Tag> : null;
});

export const ScreenTitle = observer(({ code, title, extra, sub, back }: { code: string; title: React.ReactNode; extra?: React.ReactNode; sub?: React.ReactNode; back?: React.ReactNode }) => (
  <div className="page-head">
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, flexWrap: 'wrap' }}>
      {back}
      <div style={{ minWidth: 0 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {app.techMode && <span className="mono" style={{ color: C.sec, fontWeight: 500, marginRight: 8 }}>{code}</span>}
          {title}
        </Typography.Title>
        {sub && <div style={{ color: C.sec, marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
    {extra && <Space wrap>{extra}</Space>}
  </div>
));

export function BackLink({ to, children }: { to: string; children: React.ReactNode }) {
  return <Link to={to}><Button>← {children}</Button></Link>;
}

export function KV({ items, cols = 2 }: { items: [string, React.ReactNode][]; cols?: number }) {
  return (
    <dl className="kv" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
      {items.map(([k, v]) => (
        <div key={k}><dt>{k}</dt><dd>{v === '' || v === null || v === undefined ? '—' : v}</dd></div>
      ))}
    </dl>
  );
}

export function Block({ title, children, extra }: { title: React.ReactNode; children: React.ReactNode; extra?: React.ReactNode }) {
  return <Card size="small" title={title} extra={extra} style={{ marginBottom: 12 }}>{children}</Card>;
}

export function HistoryModal({ open, onClose, rows, withFile, title }: { open: boolean; onClose: () => void; rows: any[]; withFile?: boolean; title: string }) {
  const cols: any[] = [
    { title: 'Дата', dataIndex: 'date', width: 150, render: fmtDateTime },
    { title: 'Пользователь', dataIndex: 'user' },
    { title: 'Статус', dataIndex: 'status', render: (s: string) => <StatusChip status={s} compact /> },
    ...(withFile ? [{ title: 'Приложен новый файл', dataIndex: 'file', width: 110 }] : []),
    { title: 'Комментарий', dataIndex: 'comment', render: (c: string) => c || '—' },
  ];
  return (
    <Modal open={open} onCancel={onClose} title={title} width={860} footer={<Button onClick={onClose}>Закрыть</Button>}>
      <Table size="small" rowKey={(_, i) => String(i)} columns={cols} dataSource={[...rows].reverse()} pagination={false} />
    </Modal>
  );
}

/** Решение «a / b» с обязательным комментарием для «b» (R-B301-04, R-B303-05). */
export function DecisionModal({ open, title, a, b, onClose, onSubmit, commentFor = 'b', rule }: {
  open: boolean; title: string; a: string; b: string; onClose: () => void; onSubmit: (decision: 'a' | 'b', comment: string) => Promise<void>; commentFor?: 'a' | 'b' | 'none'; rule?: string;
}) {
  const [d, setD] = useState<'a' | 'b'>('a');
  const [c, setC] = useState('');
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const req = commentFor === d;
  const close = () => { setD('a'); setC(''); setTried(false); onClose(); };
  return (
    <Modal open={open} title={title} onCancel={close} okText="Отправить" cancelText="Отмена" confirmLoading={busy} destroyOnClose
      onOk={async () => {
        if (req && !c.trim()) { setTried(true); return; }
        setBusy(true);
        try { await onSubmit(d, c.trim()); close(); } catch (e) { message.error(errText(e)); } finally { setBusy(false); }
      }}>
      <Segmented block value={d} onChange={(v) => setD(v as any)} options={[{ label: a, value: 'a' }, { label: b, value: 'b' }]} style={{ marginBottom: 12 }} />
      <div className="field-label">Комментарий {req && <span className="req">*</span>}<Rule code={rule} /></div>
      <Input.TextArea rows={3} maxLength={1000} showCount value={c} onChange={(e) => setC(e.target.value)} status={tried && req && !c.trim() ? 'error' : undefined} disabled={commentFor === 'none'} />
      {tried && req && !c.trim() && <div className="err">Укажите, что исправить</div>}
    </Modal>
  );
}

/** Выбор и загрузка файла в S3 (OQ-21). Возвращает метаданные загруженного файла. */
export function FilePick({ onUploaded, accept, label = 'Выбрать файл', entityType = 'draft', entityId = '', disabled, multiple }: {
  onUploaded: (f: { id: number; name: string; size: number }) => void; accept?: string; label?: string; entityType?: string; entityId?: string; disabled?: boolean; multiple?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Upload showUploadList={false} accept={accept} multiple={multiple} disabled={disabled}
      customRequest={async ({ file, onSuccess, onError }) => {
        setBusy(true);
        try { const r = await uploadFile(file as File, entityType, entityId); onUploaded(r); onSuccess?.(r); } catch (e) { message.error(errText(e)); onError?.(e as any); } finally { setBusy(false); }
      }}>
      <Button icon={<UploadOutlined />} loading={busy} disabled={disabled}>{label}</Button>
    </Upload>
  );
}

export function fieldErrors(e: any): Record<string, string> {
  return (e as ApiError)?.fields && typeof (e as ApiError).fields === 'object' ? ((e as ApiError).fields as Record<string, string>) : {};
}

export function showError(e: any) {
  const err = e as ApiError;
  if (err?.status && err.status >= 500) return; // уже показано интерсептором
  message.error(<span>{errText(e)}{err?.rule && app.techMode ? <Tag className="mono" style={{ marginLeft: 6 }}>{err.rule}</Tag> : null}</span>);
}

export const TOL: Record<string, { sym: string; label: string; cls: string }> = {
  ok: { sym: '●', label: 'В допуске', cls: 'tol-ok' }, borderline: { sym: '▲', label: 'На границе', cls: 'tol-bl' },
  exceeded: { sym: '◆', label: 'Вне допуска', cls: 'tol-ex' }, empty: { sym: '—', label: 'Нет замера', cls: 'tol-em' },
};
export function TolBadge({ t }: { t?: string | null }) {
  if (!t) return null;
  const m = TOL[t] || TOL.empty;
  return <span className={`tol ${m.cls}`}><span aria-hidden>{m.sym}</span>{m.label}</span>;
}
export const SEC: Record<string, { sym: string; label: string; cls: string }> = {
  not_started: { sym: '○', label: 'Не начат', cls: 'sec-ns' }, in_progress: { sym: '◐', label: 'В процессе', cls: 'sec-ip' },
  done: { sym: '✓', label: 'Пройден', cls: 'sec-done' }, skipped: { sym: '⊘', label: 'Не проводился', cls: 'sec-sk' },
};
export function SecBadge({ s }: { s: string }) {
  const m = SEC[s] || SEC.not_started;
  return <span className={`secb ${m.cls}`}><span aria-hidden>{m.sym}</span>{m.label}</span>;
}

export function NoAccess({ text }: { text?: string }) {
  return <Result status="403" title="Нет доступа" subTitle={text || 'У вашей учётной записи нет функциональной роли МП-3.5 для этого действия. Обратитесь к администратору модуля.'} />;
}

export function EmptyText({ text }: { text: string }) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={text} />;
}

export const ReadOnlyBanner = observer(({ screen }: { screen: string }) => {
  const editable = app.me?.editScreens.includes(screen);
  if (editable) return null;
  return (
    <div className="ro-banner"><EyeOutlined /> Роль «{app.me?.roles.map((r) => r.short).join(', ') || '—'}»: экран доступен для просмотра, кнопки изменения скрыты.</div>
  );
});

export function Tip({ title, children }: { title?: React.ReactNode; children: React.ReactElement }) {
  return title ? <Tooltip title={title}>{children}</Tooltip> : children;
}
