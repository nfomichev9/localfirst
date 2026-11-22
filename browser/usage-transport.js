import {browserUsage} from './analytics.js';

window.localfirstBrowser = {
  async request(path) {
    return Response.json(browserUsage(new URL(path, location.origin).search));
  },
};
await import('./usage.js');
