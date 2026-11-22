import {createBrowserTransport} from './backend.js';

const $ = id => document.getElementById(id);

export async function openChat(model, engine, options) {
  window.localfirstBrowser = createBrowserTransport(model, engine, options);
  const settings = $('browser-settings');
  $('settings-link').addEventListener('click', event => {
    event.preventDefault();
    $('workspace').open = false;
    settings.showModal();
  });
  for (const input of settings.querySelectorAll('[data-reply-detail]')) {
    input.checked = readReplyDetails()[input.dataset.replyDetail] === true;
    input.onchange = () => {
      const details = Object.fromEntries([...settings.querySelectorAll('[data-reply-detail]')]
        .map(control => [control.dataset.replyDetail, control.checked]));
      const status = $('display-status');
      try {
        localStorage.setItem(replyDetailsKey, JSON.stringify(details));
        window.dispatchEvent(new Event('localfirst-display-change'));
        status.textContent = 'Display preferences saved.';
        status.dataset.error = 'false';
      } catch {
        input.checked = !input.checked;
        status.textContent = 'This browser could not save the display preference.';
        status.dataset.error = 'true';
      }
      status.hidden = false;
    };
  }
  await import('./app.js');
  $('startup-screen').hidden = true;
  if ($('setup-screen')) $('setup-screen').hidden = true;
  $('chat-screen').hidden = false;
  $('prompt').focus();
}
