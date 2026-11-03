import { ReloadOutlined } from '@ant-design/icons';
import { Button, Result, Skeleton } from 'antd';
import React from 'react';

/** Состояния экрана Loading / Error (ТЗ: скелетон > 300 мс; баннер ошибки с кодом и кнопкой «Повторить»). */
export default function LoadState({ loading, error, reload, children }: { loading: boolean; error: any; reload: () => void; children: () => React.ReactNode }) {
  if (error) {
    if (error.status === 403) return <Result status="403" title="Нет доступа" subTitle={error.detail} />;
    if (error.status === 404) return <Result status="404" title="Не найдено" subTitle={error.detail} />;
    return (
      <div className="banner-err" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <span><b>Ошибка обращения к сервису данных (HTTP {error.status || '—'} / {error.rule || 'ERR_BDTS_API'})</b><br />{error.detail}</span>
        <Button danger icon={<ReloadOutlined />} onClick={reload}>Повторить запрос</Button>
      </div>
    );
  }
  if (loading) return <div className="panel"><Skeleton active paragraph={{ rows: 8 }} /></div>;
  return <>{children()}</>;
}
