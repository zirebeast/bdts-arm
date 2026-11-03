// Мастер загрузки технического отчёта XML v3.8: файл → вложения → проверка XSD и правил (D-TO-06, D-TO-01)
import { InboxOutlined, PaperClipOutlined } from '@ant-design/icons';
import { Button, Modal, Steps, Upload, message } from 'antd';
import { useState } from 'react';
import { download, upload } from '../api';
import { showError } from '../ui';
import IssuesPanel from './IssuesPanel';

export default function UploadWizard({ open, onClose, reportId, onDone }: { open: boolean; onClose: () => void; reportId?: number; onDone: (card: any) => void }) {
  const [step, setStep] = useState(0);
  const [xml, setXml] = useState<File | null>(null);
  const [att, setAtt] = useState<File[]>([]);
  const [check, setCheck] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const reset = () => { setStep(0); setXml(null); setAtt([]); setCheck(null); };
  const close = () => { reset(); onClose(); };
  const next = async () => {
    if (step === 0 && !xml) { message.error('Выберите XML-файл технического отчёта'); return; }
    if (step === 1) {
      setBusy(true);
      try { setCheck(await upload('/reports/check', { file: xml! })); } catch (e) { showError(e); setBusy(false); return; }
      setBusy(false);
    }
    setStep(step + 1);
  };
  const finish = async () => {
    setBusy(true);
    try {
      const card = await upload('/reports', { file: xml!, attachments: att }, reportId ? { report_id: String(reportId) } : {});
      message.success(`Загружена версия ${card.version}${card.validation?.summary?.Block ? `: ошибок L1 — ${card.validation.summary.Block}` : ', ошибок L1 нет'}`);
      reset();
      onDone(card);
    } catch (e) { showError(e); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onCancel={close} width={760} title={reportId ? 'Загрузка новой версии технического отчёта (D-TO-01)' : 'Мастер загрузки технического отчёта (XSD v3.8)'} destroyOnClose
      footer={<>
        <Button onClick={close}>Отмена</Button>
        {step > 0 && <Button onClick={() => setStep(step - 1)}>← Назад</Button>}
        {step < 2 ? <Button type="primary" loading={busy} onClick={next}>Далее →</Button>
          : <Button type="primary" loading={busy} disabled={!check?.xsdOk} style={{ background: check?.xsdOk ? '#1E7B34' : undefined }} onClick={finish}>{reportId ? 'Сохранить новую версию' : 'Загрузить и открыть карточку ТО'}</Button>}
      </>}>
      <Steps size="small" current={step} style={{ marginBottom: 16 }} items={[{ title: 'Файл XML (v3.8)' }, { title: 'Вложения (PDF, SIG)' }, { title: 'Проверка XSD и правил' }]} />
      {step === 0 && <>
        <Upload.Dragger accept=".xml" maxCount={1} beforeUpload={(f) => { setXml(f); return false; }} onRemove={() => setXml(null)} fileList={xml ? [{ uid: '1', name: xml.name, status: 'done' } as any] : []}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p>Перетащите XML-файл технического отчёта или нажмите для выбора</p>
          <p className="hint">namespace urn:gazprom-diagnostics:technical-report:3.8</p>
        </Upload.Dragger>
        <div className="hint" style={{ marginTop: 10 }}>Образцы для проверки: <a onClick={() => download('/reports/sample-xml', { kind: 'errors' })}>с ошибками L1</a> · <a onClick={() => download('/reports/sample-xml', { kind: 'fixed' })}>исправленная версия ГРС</a> · <a onClick={() => download('/reports/sample-xml', { kind: 'new' })}>новый отчёт</a></div>
      </>}
      {step === 1 && <Upload.Dragger multiple beforeUpload={(f) => { setAtt((l) => [...l, f]); return false; }} onRemove={(f) => setAtt((l) => l.filter((x) => x.name !== f.name))}
        fileList={att.map((f, i) => ({ uid: String(i), name: f.name, status: 'done' } as any))}>
        <p className="ant-upload-drag-icon"><PaperClipOutlined /></p>
        <p>Приложите скан-копии заключений, фотографии и откреплённую ЭП (.sig) — необязательно</p>
      </Upload.Dragger>}
      {step === 2 && check && (
        <div>
          {check.xsdOk
            ? <div className="banner-ok">Проверка XSD v3.8 пройдена: {check.number} · ЕО распознано: {check.eoCount}; ошибок L1 — {check.summary.Block}, предупреждений — {check.summary.Warn}; ЕО требуют сопоставления с БДО — {check.unmapped}.
              {check.exists && !reportId && ' Отчёт с таким номером уже есть — будет загружена новая версия.'}</div>
            : <div className="banner-err">XML не проходит проверку по XSD v3.8 (D-TO-06). Загрузка невозможна: исправьте файл в системе ГД.</div>}
          <IssuesPanel issues={check.issues} />
        </div>
      )}
    </Modal>
  );
}
