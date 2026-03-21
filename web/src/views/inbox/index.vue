<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  createInboxMessage,
  fetchInboxChannels,
  fetchMarketplaceInbox,
  getStoredAccessToken,
  markInboxMessagesRead
} from '@/service/api';
import { getLocale } from '@/locales';
import MessageCard from './MessageCard.vue';

const isZh = computed(() => getLocale() === 'zh-CN');
const activeChannel = ref('all');
const query = ref('');
const msgs = ref<any[]>([]);
const channels = ref<any[]>([]);
const selectedIds = ref(new Set<string>());
const page = ref(1);
const pageSize = ref(10);
const ingesting = ref(false);

const webhookPayload = ref('{\n  "title": "Webhook message",\n  "body": "Received from third-party notification API",\n  "category": "workspace",\n  "channel": "webhook",\n  "source": "notification-api"\n}');

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase();
  return msgs.value.filter(item => {
    const channelPass = activeChannel.value === 'all' || item.channel === activeChannel.value;
    const queryPass = !q || `${item.title} ${item.body} ${item.category} ${item.channel}`.toLowerCase().includes(q);
    return channelPass && queryPass;
  });
});

const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
const paged = computed(() => {
  page.value = Math.min(page.value, pageCount.value);
  const start = (page.value - 1) * pageSize.value;
  return filtered.value.slice(start, start + pageSize.value);
});

const channelOptions = computed(() => [
  { label: isZh.value ? '全部渠道' : 'All channels', value: 'all' },
  ...channels.value.map(item => ({ label: `${item.channel} (${item.count})`, value: item.channel }))
]);

function t(zh: string, en: string) {
  return isZh.value ? zh : en;
}

async function loadMessages() {
  msgs.value = await fetchMarketplaceInbox(activeChannel.value === 'all' ? undefined : { channel: activeChannel.value });
}

async function loadChannels() {
  channels.value = await fetchInboxChannels(getStoredAccessToken() || undefined);
}

async function refreshAll() {
  try {
    await Promise.all([loadMessages(), loadChannels()]);
  } catch {
    msgs.value = [];
    channels.value = [];
  }
}

function toggleSelect(id: string) {
  if (selectedIds.value.has(id)) selectedIds.value.delete(id);
  else selectedIds.value.add(id);
}

async function markRead() {
  const ids = [...selectedIds.value].map(Number);
  if (!ids.length) return;
  await markInboxMessagesRead(ids, true, getStoredAccessToken() || undefined);
  selectedIds.value.clear();
  await refreshAll();
}

function openMessage(message: any) {
  window.$dialog?.info({
    title: message.title,
    content: message.body,
    positiveText: 'Close'
  });
}

async function createContextMessage() {
  ingesting.value = true;
  try {
    await createInboxMessage(
      {
        title: t('右键接收的消息', 'Context Menu Message'),
        body: t('来自页面右键操作的手动消息。', 'Manually created from the page context menu.'),
        category: 'workspace',
        channel: 'context-menu',
        source: 'context-menu'
      },
      getStoredAccessToken() || undefined
    );
    window.$message?.success(t('已创建右键消息', 'Context message created'));
    await refreshAll();
  } finally {
    ingesting.value = false;
  }
}

async function receiveClipboardFile(event: ClipboardEvent) {
  const files = event.clipboardData?.files ? Array.from(event.clipboardData.files) : [];
  const file = files[0];
  if (!file) return;
  event.preventDefault();
  await createInboxMessage(
    {
      title: t('粘贴接收文件', 'Pasted File'),
      body: t(`接收到文件 ${file.name}`, `Received file ${file.name}`),
      category: 'workspace',
      channel: 'clipboard',
      source: 'clipboard',
      attachments: [{ name: file.name, type: file.type, size: file.size }]
    },
    getStoredAccessToken() || undefined
  );
  await refreshAll();
}

async function receiveDroppedFile(event: DragEvent) {
  event.preventDefault();
  const files = event.dataTransfer?.files ? Array.from(event.dataTransfer.files) : [];
  const file = files[0];
  if (!file) return;
  await createInboxMessage(
    {
      title: t('拖拽接收文件', 'Dropped File'),
      body: t(`拖拽接收到文件 ${file.name}`, `Received file ${file.name} from drag and drop`),
      category: 'workspace',
      channel: 'drop-file',
      source: 'drag-drop',
      attachments: [{ name: file.name, type: file.type, size: file.size }]
    },
    getStoredAccessToken() || undefined
  );
  await refreshAll();
}

async function triggerBrowserNotification() {
  if (!('Notification' in window)) {
    return (window as any).$message?.warning(t('当前浏览器不支持通知 API', 'Notification API is not supported'));
  }
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    return (window as any).$message?.warning(t('通知权限未授予', 'Notification permission denied'));
  }
  const notification = new Notification(t('收件箱通知测试', 'Inbox Notification Test'), {
    body: t('通知 API 已就绪，可以结合第三方服务推送消息。', 'Notification API is ready for third-party pushes.')
  });
  notification.onclick = async () => {
    window.focus();
    await createInboxMessage(
      {
        title: t('通知 API 回执', 'Notification API Receipt'),
        body: t('用户点击了浏览器通知。', 'The user clicked the browser notification.'),
        category: 'routing',
        channel: 'notification-api',
        source: 'notification-api'
      },
      getStoredAccessToken() || undefined
    );
    await refreshAll();
  };
}

async function ingestWebhookPayload() {
  ingesting.value = true;
  try {
    const payload = JSON.parse(webhookPayload.value);
    await createInboxMessage(payload, getStoredAccessToken() || undefined, true);
    window.$message?.success(t('已通过通知 API 示例写入消息', 'Notification API example message sent'));
    await refreshAll();
  } catch (error: any) {
    window.$message?.error(error?.message || t('Webhook 示例写入失败', 'Failed to send webhook example'));
  } finally {
    ingesting.value = false;
  }
}

onMounted(async () => {
  await refreshAll();
  window.addEventListener('paste', receiveClipboardFile);
});

onBeforeUnmount(() => {
  window.removeEventListener('paste', receiveClipboardFile);
});
</script>

<template>
  <div class="inbox-page" @drop="receiveDroppedFile" @dragover.prevent @contextmenu.prevent="createContextMessage">
    <div class="hero-card">
      <div>
        <div class="hero-kicker">Inbox</div>
        <div class="hero-title">{{ t('消息渠道与接入中心', 'Message Channels And Intake') }}</div>
        <div class="hero-desc">
          {{ t('支持筛选消息渠道、右键创建消息、粘贴或拖拽接收文件，并提供第三方通知 API 的接入示例。', 'Filter message channels, create context messages, receive files by paste or drag-drop, and test a third-party notification API flow.') }}
        </div>
      </div>
      <NTag type="info" round>{{ msgs.length }} {{ t('条消息', 'messages') }}</NTag>
    </div>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:15">
        <div class="panel-card">
          <div class="header-row">
            <n-input v-model:value="query" size="medium" :placeholder="t('搜索消息、渠道或分类', 'Search messages, channels or categories')" clearable style="flex:1" />
            <n-select v-model:value="activeChannel" :options="channelOptions" style="width: 180px" @update:value="refreshAll" />
            <div class="toolbar-actions">
              <n-button size="small" @click="markRead">{{ t('标记已读', 'Mark Read') }}</n-button>
              <n-button size="small" secondary @click="refreshAll">{{ t('刷新', 'Refresh') }}</n-button>
            </div>
          </div>

          <div class="list-area">
            <div v-if="filtered.length === 0" class="empty">{{ t('暂无消息', 'No messages') }}</div>
            <div v-else>
              <MessageCard
                v-for="m in paged"
                :key="m.id"
                :message="{
                  ...m,
                  id: String(m.id),
                  subject: m.title,
                  snippet: m.body,
                  fileType: m.channel,
                  module: m.category,
                  date: new Date(m.created_at || Date.now()).getTime()
                }"
                :selected="selectedIds.has(String(m.id))"
                @toggle="toggleSelect"
                @open="openMessage"
              />
            </div>
          </div>

          <div class="pager-row">
            <div class="summary">{{ t('已选', 'Selected') }} {{ selectedIds.size }}</div>
            <n-pagination :page="page" :page-count="pageCount" @update:page="p => page = p" />
          </div>
        </div>
      </NGi>

      <NGi span="24 s:24 m:9">
        <div class="panel-card side-panel">
          <div class="side-title">{{ t('渠道选项', 'Channel Options') }}</div>
          <div class="channel-list">
            <div v-for="item in channels" :key="item.channel" class="channel-card">
              <div>
                <div class="channel-name">{{ item.channel }}</div>
                <div class="channel-meta">{{ item.unread }} {{ t('未读', 'unread') }}</div>
              </div>
              <NTag round type="warning">{{ item.count }}</NTag>
            </div>
          </div>

          <div class="action-group">
            <NButton block secondary :loading="ingesting" @click="createContextMessage">{{ t('右键消息示例', 'Context Menu Example') }}</NButton>
            <NButton block secondary @click="triggerBrowserNotification">{{ t('通知 API 测试', 'Notification API Test') }}</NButton>
          </div>

          <div class="webhook-box">
            <div class="side-title">{{ t('第三方通知 API 示例', 'Third-party Notification API Example') }}</div>
            <div class="webhook-tip">
              {{ t('向 /api/inbox/ingest 发送 JSON 即可写入收件箱；当前示例会使用已登录用户的 Token。', 'POST JSON to /api/inbox/ingest to write into inbox; this example uses the signed-in token.') }}
            </div>
            <NInput v-model:value="webhookPayload" type="textarea" :autosize="{ minRows: 9, maxRows: 14 }" />
            <NButton type="primary" block :loading="ingesting" @click="ingestWebhookPayload">{{ t('发送示例请求', 'Send Example Request') }}</NButton>
          </div>
        </div>
      </NGi>
    </NGrid>
  </div>
</template>

<style scoped>
.inbox-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hero-card,
.panel-card,
.channel-card {
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.hero-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
}

.hero-kicker,
.hero-desc,
.summary,
.channel-meta,
.webhook-tip {
  color: #64748b;
  font-size: 12px;
}

.hero-title,
.side-title,
.channel-name {
  margin: 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.side-title,
.channel-name {
  font-size: 16px;
  margin: 0;
}

.panel-card {
  padding: 16px;
}

.header-row,
.toolbar-actions,
.pager-row,
.channel-card {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-actions {
  margin-left: auto;
}

.list-area {
  margin-top: 12px;
  background: var(--n-card-color, #fff);
  border-radius: 16px;
  padding: 8px;
  max-height: 60vh;
  overflow: auto;
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.empty {
  padding: 40px;
  text-align: center;
  color: var(--n-text-3);
}

.pager-row {
  justify-content: space-between;
  margin-top: 12px;
}

.side-panel,
.channel-list,
.action-group,
.webhook-box {
  display: grid;
  gap: 12px;
}

.channel-card {
  justify-content: space-between;
  padding: 14px;
}

@media (prefers-color-scheme: dark) {
  .hero-card,
  .panel-card,
  .list-area,
  .channel-card {
    background: rgba(15, 23, 42, 0.82);
    border-color: rgba(71, 85, 105, 0.3);
  }

  .hero-title,
  .side-title,
  .channel-name {
    color: #e2e8f0;
  }

  .hero-kicker,
  .hero-desc,
  .summary,
  .channel-meta,
  .webhook-tip {
    color: #94a3b8;
  }
}
</style>
