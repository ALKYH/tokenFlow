<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  classifyRoutingMessage,
  fetchRoutingRules,
  fetchRoutingSummary,
  getStoredAccessToken,
  resolveRoutingContext,
  saveRoutingRule,
  updateRoutingRule
} from '@/service/api';
import { getLocale } from '@/locales';

const rules = ref<any[]>([]);
const summary = ref({ categories: ['general'], channels: ['dashboard'], rule_count: 0, enabled_count: 0 });
const loading = ref(false);
const classifyLoading = ref(false);
const savingRule = ref(false);
const selectedCategory = ref('billing');
const selectedChannel = ref('email');
const messageText = ref('Customer asks for invoice reissue because payment failed.');
const fileType = ref('workspace');
const classifierMode = ref<'rule' | 'ai'>('rule');
const classificationResult = ref<any | null>(null);
const draftRule = ref({
  name: 'New Personal Rule',
  category: 'workspace',
  channel: 'dashboard',
  matcher_type: 'keyword',
  matcher_config: { keywords: ['module', 'workflow'] },
  action_config: { target: 'personal-library', priority: 'medium' },
  classifier_mode: 'rule',
  priority: 90,
  enabled: true,
  is_public: false
});
const matcherKeywordsText = ref('module\nworkflow');
const actionConfigText = ref('{\n  "target": "personal-library",\n  "priority": "medium"\n}');
const editingRuleId = ref<number | null>(null);
const isZh = computed(() => getLocale() === 'zh-CN');

const groupedRules = computed(() =>
  summary.value.categories.map(category => ({
    category,
    items: rules.value.filter(rule => rule.category === category)
  }))
);

function t(zh: string, en: string) {
  return isZh.value ? zh : en;
}

async function loadRules() {
  loading.value = true;
  try {
    const token = getStoredAccessToken() || undefined;
    const [rulesData, summaryData] = await Promise.all([fetchRoutingRules(token), fetchRoutingSummary(token)]);
    rules.value = rulesData;
    summary.value = summaryData;
    selectedCategory.value = summaryData.categories[0] || selectedCategory.value;
    selectedChannel.value = summaryData.channels[0] || selectedChannel.value;
  } catch {
    rules.value = [];
  } finally {
    loading.value = false;
  }
}

async function runClassifier() {
  classifyLoading.value = true;
  try {
    const resolved = await resolveRoutingContext(
      {
        category: selectedCategory.value,
        channel: selectedChannel.value,
        file_name: 'workspace.json',
        file_type: fileType.value
      },
      getStoredAccessToken() || undefined
    );

    const result = await classifyRoutingMessage({
      category: resolved.resolved_category,
      channel: resolved.resolved_channel,
      text: messageText.value,
      use_ai: classifierMode.value === 'ai',
      file_name: 'workspace.json',
      file_type: fileType.value
    });

    classificationResult.value = {
      ...result,
      resolved
    };
  } catch (error: any) {
    classificationResult.value = {
      matched: false,
      mode: classifierMode.value,
      reason: error?.message || 'Classification failed',
      target: {}
    };
  } finally {
    classifyLoading.value = false;
  }
}

function useRuleAsDraft(rule: any) {
  editingRuleId.value = rule.id;
  draftRule.value = {
    name: rule.name,
    category: rule.category,
    channel: rule.channel,
    matcher_type: rule.matcher_type,
    matcher_config: rule.matcher_config || { keywords: [] },
    action_config: rule.action_config || {},
    classifier_mode: rule.classifier_mode,
    priority: rule.priority,
    enabled: rule.enabled,
    is_public: rule.is_public
  };
  matcherKeywordsText.value = (rule.matcher_config?.keywords || []).join('\n');
  actionConfigText.value = JSON.stringify(rule.action_config || {}, null, 2);
}

async function submitRule() {
  savingRule.value = true;
  try {
    draftRule.value.matcher_config = {
      keywords: matcherKeywordsText.value.split('\n').map(item => item.trim()).filter(Boolean)
    };
    draftRule.value.action_config = JSON.parse(actionConfigText.value || '{}');
    const token = getStoredAccessToken() || undefined;
    if (editingRuleId.value) {
      await updateRoutingRule(editingRuleId.value, draftRule.value, token);
      window.$message?.success(t('路由规则已更新', 'Routing rule updated'));
    } else {
      await saveRoutingRule(draftRule.value, token);
      window.$message?.success(t('路由规则已创建', 'Routing rule created'));
    }
    editingRuleId.value = null;
    await loadRules();
  } catch (error: any) {
    window.$message?.error(error?.message || t('保存规则失败', 'Failed to save rule'));
  } finally {
    savingRule.value = false;
  }
}

onMounted(loadRules);
</script>

<template>
  <div class="routing-page">
    <div class="hero-card">
      <div>
        <div class="hero-kicker">Routing Center</div>
        <div class="hero-title">{{ t('路由规则与分类控制台', 'Routing Rules And Classification Console') }}</div>
        <div class="hero-desc">
          {{ t('修复后的路由页会同时展示规则概览、上下文解析结果、分类测试，以及个人路由规则的新建与更新。', 'The routing page now shows rule summaries, resolved routing context, classifier tests, and personal rule creation/update.') }}
        </div>
      </div>
      <div class="hero-stats">
        <NTag round type="info">{{ t('规则', 'Rules') }} {{ summary.rule_count }}</NTag>
        <NTag round type="success">{{ t('启用', 'Enabled') }} {{ summary.enabled_count }}</NTag>
      </div>
    </div>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:14">
        <NCard :bordered="false" class="panel-card">
          <template #header>{{ t('规则目录', 'Rule Catalog') }}</template>
          <NSpin :show="loading">
            <div class="summary-row">
              <NTag v-for="item in summary.categories" :key="item" round>{{ item }}</NTag>
            </div>
            <div class="rule-groups">
              <div v-for="group in groupedRules" :key="group.category" class="rule-group">
                <div class="group-head">
                  <div class="group-title">{{ group.category }}</div>
                  <NTag round>{{ group.items.length }}</NTag>
                </div>
                <div v-if="group.items.length" class="rule-list">
                  <div v-for="rule in group.items" :key="rule.id" class="rule-card" @click="useRuleAsDraft(rule)">
                    <div class="rule-title">{{ rule.name }}</div>
                    <div class="rule-meta">{{ t('渠道', 'Channel') }} {{ rule.channel }} · {{ t('优先级', 'Priority') }} {{ rule.priority }}</div>
                    <div class="rule-keywords">
                      <NTag v-for="keyword in rule.matcher_config?.keywords || []" :key="keyword" size="small" round>{{ keyword }}</NTag>
                    </div>
                    <div class="rule-target">{{ t('目标', 'Target') }} {{ rule.action_config?.target || 'unassigned' }}</div>
                  </div>
                </div>
                <NEmpty v-else size="small" :description="t('当前分类暂无规则', 'No rules in this category')" />
              </div>
            </div>
          </NSpin>
        </NCard>
      </NGi>

      <NGi span="24 s:24 m:10">
        <NCard :bordered="false" class="panel-card">
          <template #header>{{ t('路由测试', 'Routing Test') }}</template>

          <NForm label-placement="top">
            <NFormItem :label="t('分类', 'Category')">
              <NSelect v-model:value="selectedCategory" :options="summary.categories.map(item => ({ label: item, value: item }))" />
            </NFormItem>
            <NFormItem :label="t('渠道', 'Channel')">
              <NSelect v-model:value="selectedChannel" :options="summary.channels.map(item => ({ label: item, value: item }))" />
            </NFormItem>
            <NFormItem :label="t('文件类型', 'File Type')">
              <NSelect
                v-model:value="fileType"
                :options="['workspace', 'module', 'workflow', 'pdf', 'image', 'audio'].map(item => ({ label: item, value: item }))"
              />
            </NFormItem>
            <NFormItem :label="t('分类器', 'Classifier')">
              <NSegmented v-model:value="classifierMode" :options="[{ label: 'Rule', value: 'rule' }, { label: 'AI', value: 'ai' }]" />
            </NFormItem>
            <NFormItem :label="t('输入内容', 'Input')">
              <NInput v-model:value="messageText" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }" />
            </NFormItem>
            <NButton type="primary" :loading="classifyLoading" @click="runClassifier">{{ t('运行分类', 'Run Classifier') }}</NButton>
          </NForm>

          <div class="result-card" :class="{ matched: classificationResult?.matched, miss: classificationResult && !classificationResult?.matched }">
            <div class="result-title">{{ t('结果', 'Result') }}</div>
            <div v-if="classificationResult" class="result-body">
              <div>{{ t('模式', 'Mode') }}: {{ classificationResult.mode }}</div>
              <div>{{ t('命中', 'Matched') }}: {{ classificationResult.matched ? t('是', 'Yes') : t('否', 'No') }}</div>
              <div>{{ t('规则', 'Rule') }}: {{ classificationResult.rule_name || '-' }}</div>
              <div>{{ t('原因', 'Reason') }}: {{ classificationResult.reason || '-' }}</div>
              <div>{{ t('解析分类', 'Resolved Category') }}: {{ classificationResult.resolved?.resolved_category || classificationResult.resolved_category || '-' }}</div>
              <div>{{ t('解析渠道', 'Resolved Channel') }}: {{ classificationResult.resolved?.resolved_channel || classificationResult.resolved_channel || '-' }}</div>
              <div>{{ t('路由类型', 'Route Kind') }}: {{ classificationResult.route_kind || classificationResult.resolved?.route_kind || '-' }}</div>
            </div>
            <NEmpty v-else size="small" :description="t('运行分类后显示结果', 'Run the classifier to see a result')" />
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <NCard :bordered="false" class="panel-card">
      <template #header>{{ editingRuleId ? t('编辑个人规则', 'Edit Personal Rule') : t('新建个人规则', 'Create Personal Rule') }}</template>
      <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
        <NGi span="24 s:24 m:8">
          <NForm label-placement="top">
            <NFormItem :label="t('规则名称', 'Rule Name')">
              <NInput v-model:value="draftRule.name" />
            </NFormItem>
            <NFormItem :label="t('分类', 'Category')">
              <NInput v-model:value="draftRule.category" />
            </NFormItem>
            <NFormItem :label="t('渠道', 'Channel')">
              <NInput v-model:value="draftRule.channel" />
            </NFormItem>
          </NForm>
        </NGi>
        <NGi span="24 s:24 m:8">
          <NForm label-placement="top">
            <NFormItem :label="t('关键词列表 JSON', 'Keyword JSON')">
              <NInput v-model:value="matcherKeywordsText" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }" />
            </NFormItem>
          </NForm>
        </NGi>
        <NGi span="24 s:24 m:8">
          <NForm label-placement="top">
            <NFormItem :label="t('动作配置 JSON', 'Action JSON')">
              <NInput v-model:value="actionConfigText" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }" />
            </NFormItem>
            <NButton type="primary" :loading="savingRule" @click="submitRule">{{ t('保存规则', 'Save Rule') }}</NButton>
          </NForm>
        </NGi>
      </NGrid>
    </NCard>
  </div>
</template>

<style scoped>
.routing-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-card,
.panel-card,
.rule-card,
.result-card {
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.86);
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
.rule-meta,
.rule-target {
  color: #64748b;
  font-size: 12px;
}

.hero-title,
.group-title,
.rule-title,
.result-title {
  font-weight: 700;
  color: #0f172a;
}

.hero-title {
  font-size: 26px;
  margin: 8px 0;
}

.hero-stats,
.summary-row,
.rule-groups,
.rule-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.rule-groups {
  display: grid;
}

.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.rule-card,
.result-card {
  padding: 14px;
}

.rule-card {
  cursor: pointer;
}

.rule-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.result-card {
  margin-top: 16px;
}

.result-card.matched {
  border-color: rgba(34, 197, 94, 0.24);
  background: rgba(240, 253, 244, 0.92);
}

.result-card.miss {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.92);
}

.result-body {
  display: grid;
  gap: 8px;
  color: #334155;
  line-height: 1.6;
}

@media (prefers-color-scheme: dark) {
  .hero-card,
  .panel-card,
  .rule-card,
  .result-card {
    background: rgba(15, 23, 42, 0.8);
    border-color: rgba(71, 85, 105, 0.3);
  }

  .hero-title,
  .group-title,
  .rule-title,
  .result-title,
  .result-body {
    color: #e2e8f0;
  }

  .hero-kicker,
  .hero-desc,
  .rule-meta,
  .rule-target {
    color: #94a3b8;
  }
}
</style>
