'use strict';

const replyDetailsKey = 'localfirst.replyDetails';
const replyDetailFields = ['model', 'timing', 'tokens'];

function readReplyDetails() {
  try {
    const saved = JSON.parse(localStorage.getItem(replyDetailsKey));
    return Object.fromEntries(replyDetailFields.map(key => [key, saved?.[key] === true]));
  } catch {
    return {};
  }
}
