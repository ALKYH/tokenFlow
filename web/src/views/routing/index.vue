<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { classifyRoutingMessage, fetchRoutingRules, getTokenflowApiUrl } from '@/service/api';
import { getLocale } from '@/locales';

const rules = ref<any[]>([]);
const loading = ref(false);
const classifyLoading = ref(false);
const selectedCategory = ref('billing');
const selectedChannel = ref('email');
const messageText = ref('Customer asks for invoice reissue because payment failed.');
const classifierMode = ref<'rule' | 'ai'>('rule');
const aiEndpoint = ref('');
const apiKey = ref('');
const classificationResult = ref<any | null>(null);
const isZh = computed(() => getLocale() === 'zh-CN');

const categories = ['billing', 'marketplace', 'knowledge'];
const channels = ['email', 'community', 'api'];

const groupedRules = computed(() =>
  categories.map(category => ({
    category,
    items: rules.value.filter(rule => rule.category === category)
  }))
);

async function loadRules() {
  loading.value = true;
  try {
    rules.value = await fetchRoutingRules();
  } catch {
    rules.value = [];
  } finally {
    loading.value = false;
  }
}

async function runClassifier() {
  classifyLoading.value = true;
  try {
    classificationResult.value = await classifyRoutingMessage({
      category: selectedCategory.value,
      channel: selectedChannel.value,
      text: messageText.value,
      use_ai: classifierMode.value === 'ai',
      ai_endpoint: classifierMode.value === 'ai' ? aiEndpoint.value : undefined,
      api_key: classifierMode.value === 'ai' ? apiKey.value : undefined
    });
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

onMounted(() => {
  aiEndpoint.value = `${getTokenflowApiUrl()}/v1/chat/completions`;
  loadRules();
});
</script>

<template>
  <div class="routing-page">
    <div class="hero-card">
      <div>
        <div class="hero-kicker">Routing Center</div>
        <div class="hero-title">{{ isZh ? '渠道规则与分类器' : 'Channel Rules And Classifiers' }}</div>
        <div class="hero-desc">{{ isZh ? '为指定分类与接收渠道编排规则，并在规则分类器与 AI 分类器之间切换测试。' : 'Bind category-specific channels to rule lists, then verify them with either a rule engine or an AI classifier.' }}</div>
      </div>
      <NTag type="info" round>{{ isZh ? '规则' : 'Rules' }} {{ rules.length }}</NTag>
    </div>

    <NGrid :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:14">
        <NCard :bordered="false" class="panel-card">
          <template #header>{{ isZh ? '规则列表' : 'Rule Catalog' }}</template>
          <NSpin :show="loading">
            <div class="rule-groups">
              <div v-for="group in groupedRules" :key="group.category" class="rule-group">
                <div class="group-head">
                  <div class="group-title">{{ group.category }}</div>
                  <NTag round>{{ group.items.length }}</NTag>
                </div>
                <div v-if="group.items.length" class="rule-list">
                  <div v-for="rule in group.items" :key="rule.id" class="rule-card">
                    <div class="rule-title">{{ rule.name }}</div>
                    <div class="rule-meta">{{ isZh ? '渠道' : 'Channel' }} {{ rule.channel }} - {{ isZh ? '优先级' : 'Priority' }} {{ rule.priority }}</div>
                    <div class="rule-keywords">
                      <NTag v-for="keyword in rule.matcher_config?.keywords || []" :key="keyword" size="small" round>{{ keyword }}</NTag>
                    </div>
                    <div class="rule-target">{{ isZh ? '目标' : 'Target' }} {{ rule.action_config?.target || 'unassigned' }}</div>
                  </div>
                </div>
                <NEmpty v-else size="small" :description="isZh ? '当前分类暂无规则' : 'No rules in this category'" />
              </div>
            </div>
          </NSpin>
        </NCard>
      </NGi>

      <NGi span="24 s:24 m:10">
        <NCard :bordered="false" class="panel-card">
          <template #header>{{ isZh ? '分类测试' : 'Classifier Test' }}</template>

          <NForm label-placement="top">
            <NFormItem :label="isZh ? '分类' : 'Category'">
              <NSelect v-model:value="selectedCategory" :options="categories.map(item => ({ label: item, value: item }))" />
            </NFormItem>
            <NFormItem :label="isZh ? '渠道' : 'Channel'">
              <NSelect v-model:value="selectedChannel" :options="channels.map(item => ({ label: item, value: item }))" />
            </NFormItem>
            <NFormItem :label="isZh ? '分类器' : 'Classifier'">
              <NSegmented v-model:value="classifierMode" :options="[{ label: 'Rule', value: 'rule' }, { label: 'AI', value: 'ai' }]" />
            </NFormItem>
            <NFormItem v-if="classifierMode === 'ai'" :label="isZh ? 'AI 接口地址' : 'AI Endpoint'">
              <NInput v-model:value="aiEndpoint" placeholder="https://.../v1/chat/completions" />
            </NFormItem>
            <NFormItem v-if="classifierMode === 'ai'" label="API Key">
              <NInput v-model:value="apiKey" type="password" show-password-on="click" />
            </NFormItem>
            <NFormItem :label="isZh ? '输入内容' : 'Input'">
              <NInput v-model:value="messageText" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }" />
            </NFormItem>
            <NButton type="primary" :loading="classifyLoading" @click="runClassifier">{{ isZh ? '运行分类' : 'Run Classifier' }}</NButton>
          </NForm>

          <div class="result-card" :class="{ matched: classificationResult?.matched, miss: classificationResult && !classificationResult?.matched }">
            <div class="result-title">{{ isZh ? '结果' : 'Result' }}</div>
            <div v-if="classificationResult" class="result-body">
              <div>{{ isZh ? '模式' : 'Mode' }}: {{ classificationResult.mode }}</div>
              <div>{{ isZh ? '命中' : 'Matched' }}: {{ classificationResult.matched ? (isZh ? '是' : 'Yes') : (isZh ? '否' : 'No') }}</div>
              <div>{{ isZh ? '规则' : 'Rule' }}: {{ classificationResult.rule_name || '-' }}</div>
              <div>{{ isZh ? '原因' : 'Reason' }}: {{ classificationResult.reason || '-' }}</div>
              <div>{{ isZh ? '目标' : 'Target' }}: {{ classificationResult.target?.target || '-' }}</div>
            </div>
            <NEmpty v-else size="small" :description="isZh ? '运行后显示分类结果' : 'Run the classifier to see a result'" />
          </div>
        </NCard>
      </NGi>
    </NGrid>
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

.rule-groups,
.rule-list {
  display: grid;
  gap: 12px;
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
