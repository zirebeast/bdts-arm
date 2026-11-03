import { App as AntApp, ConfigProvider } from 'antd';
import ruRU from 'antd/locale/ru_RU';
import dayjs from 'dayjs';
import 'dayjs/locale/ru';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { initAuth } from './auth';
import DevLogin from './pages/DevLogin';
import './assets/fonts/medeo/medeo.css';
import './styles.css';

dayjs.locale('ru');

const theme = {
  token: {
    colorPrimary: '#1F5FAD', colorText: '#1B1F24', colorTextSecondary: '#5A6472', colorBorder: '#D5DAE1', colorBgLayout: '#F4F6F8',
    colorSuccess: '#1E7B34', colorWarning: '#B54708', colorError: '#B42318', colorInfo: '#1565C0',
    borderRadius: 4, borderRadiusLG: 8, fontSize: 14, controlHeight: 32,
    fontFamily: '"Medeo Sans", sans-serif', fontFamilyCode: '"Medeo Mono", monospace',
  },
  components: { Table: { cellPaddingBlockSM: 6, cellPaddingInlineSM: 8, headerBg: '#F8FAFC' }, Menu: { itemHeight: 36, itemMarginInline: 6 } },
};

const root = createRoot(document.getElementById('root')!);

initAuth().then((state) => {
  root.render(
    <React.StrictMode>
      <ConfigProvider locale={ruRU} theme={theme}>
        <AntApp>
          {state === 'login' ? <DevLogin /> : <BrowserRouter><App /></BrowserRouter>}
        </AntApp>
      </ConfigProvider>
    </React.StrictMode>,
  );
}).catch((e) => {
  root.render(<div style={{ padding: 24 }}>Ошибка авторизации: {String(e?.message || e)}. <a href="/">Повторить</a></div>);
});
