<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import { useRouterPush } from '@/hooks/common/router';
import { getLocale, setLocale } from '@/locales';
import { fetchMyProfile, getStoredAccessToken, updateMyProfile } from '@/service/api';

defineOptions({
  name: 'UserAvatar'
});

type ApiKeyFormItem = {
  provider: string;
  secret_name: string;
  request_prefix: string;
  priority: number;
  api_key: string;
  is_active: boolean;
};

const authStore = useAuthStore();
const { toLogin } = useRouterPush();
const isZh = computed(() => getLocale() === 'zh-CN');
const showProfile = ref(false);
const saving = ref(false);
const loadingProfile = ref(false);
const profileForm = reactive({
  display_name: '',
  bio: '',
  preferredLanguage: getLocale(),
  preferredModel: 'gpt-4o-mini',
  apiKeys: [] as ApiKeyFormItem[],
  defaultApiName: '',
  hasApiKey: false
});

function t(zh: string, en: string) {
  return isZh.value ? zh : en;
}

function createDefaultApiItem(index = 1): ApiKeyFormItem {
  return {
    provider: 'openai',
    secret_name: index === 1 ? 'default' : `api_${index}`,
    request_prefix: '',
    priority: index,
    api_key: '',
    is_active: true
  };
}

function resetProfileForm() {
  profileForm.display_name = authStore.userInfo.userName || 'TokenFlow User';
  profileForm.bio = '';
  profileForm.preferredLanguage = getLocale();
  profileForm.preferredModel = 'gpt-4o-mini';
  profileForm.apiKeys = [createDefaultApiItem()];
  profileForm.defaultApiName = 'default';
  profileForm.hasApiKey = false;
}

function loginOrRegister() {
  toLogin();
}

async function openProfile() {
  showProfile.value = true;
  resetProfileForm();

  const token = getStoredAccessToken();
  if (!token) return;

  loadingProfile.value = true;
  try {
    const data = await fetchMyProfile(token);
    profileForm.display_name = data.display_name || profileForm.display_name;
    profileForm.bio = data.bio || '';
    profileForm.preferredLanguage = data.preferences?.preferredLanguage || getLocale();
    profileForm.preferredModel = data.preferences?.preferredModel || 'gpt-4o-mini';
    profileForm.apiKeys = data.api_keys?.length
      ? data.api_keys.map((item: any, index: number) => ({
          provider: item.provider || 'openai',
          secret_name: item.secret_name || `api_${index + 1}`,
          request_prefix: item.request_prefix || '',
          priority: Number(item.priority || index + 1),
          api_key: '',
          is_active: item.is_active !== false
        }))
      : [createDefaultApiItem()];
    profileForm.defaultApiName = data.default_api_name || profileForm.apiKeys[0]?.secret_name || 'default';
    profileForm.hasApiKey = !!data.has_api_key;
  } catch {
    window.$message?.warning(t('云端个人资料暂不可用，当前显示本地值。', 'Cloud profile is unavailable, local values are shown.'));
  } finally {
    loadingProfile.value = false;
  }
}

function addApiKeyRow() {
  profileForm.apiKeys.push(createDefaultApiItem(profileForm.apiKeys.length + 1));
}

function removeApiKeyRow(index: number) {
  const removed = profileForm.apiKeys[index];
  profileForm.apiKeys.splice(index, 1);
  if (!profileForm.apiKeys.length) {
    profileForm.apiKeys.push(createDefaultApiItem());
  }
  if (profileForm.defaultApiName === removed?.secret_name) {
    profileForm.defaultApiName = profileForm.apiKeys[0]?.secret_name || 'default';
  }
}

async function saveProfile() {
  const token = getStoredAccessToken();
  if (!token) {
    window.$message?.warning(t('请先登录，再同步个人偏好到云端。', 'Please sign in to sync profile preferences to cloud.'));
    return;
  }

  const apiKeys = profileForm.apiKeys
    .filter(item => item.secret_name.trim())
    .sort((a, b) => a.priority - b.priority)
    .map((item, index) => ({
      provider: item.provider || 'openai',
      secret_name: item.secret_name.trim(),
      request_prefix: item.request_prefix.trim(),
      priority: Number(item.priority || index + 1),
      api_key: item.api_key || undefined,
      is_active: item.is_active !== false
    }));

  if (!apiKeys.length) {
    window.$message?.warning(t('至少需要保留一个 API 配置。', 'At least one API configuration is required.'));
    return;
  }

  saving.value = true;
  try {
    await updateMyProfile(
      {
        display_name: profileForm.display_name,
        bio: profileForm.bio,
        preferences: {
          preferredLanguage: profileForm.preferredLanguage,
          preferredModel: profileForm.preferredModel,
          defaultApiName: profileForm.defaultApiName || apiKeys[0]?.secret_name
        },
        api_keys: apiKeys
      },
      token
    );
    setLocale(profileForm.preferredLanguage as App.I18n.LangType);
    profileForm.apiKeys = profileForm.apiKeys.map(item => ({ ...item, api_key: '' }));
    profileForm.hasApiKey = true;
    window.$message?.success(t('个人资料已保存', 'Profile saved'));
    showProfile.value = false;
  } catch {
    window.$message?.error(t('个人资料保存失败', 'Profile save failed'));
  } finally {
    saving.value = false;
  }
}

function logout() {
  window.$dialog?.info({
    title: t('确认', 'Confirm'),
    content: t('确定退出当前会话吗？', 'Sign out from current session?'),
    positiveText: t('退出登录', 'Logout'),
    negativeText: t('取消', 'Cancel'),
    onPositiveClick: () => {
      authStore.resetStore();
    }
  });
}
</script>

<template>
  <NButton v-if="!authStore.isLogin" quaternary @click="loginOrRegister">{{ t('登录 / 注册', 'Login / Register') }}</NButton>
  <div v-else>
    <ButtonIcon @click="openProfile">
      <SvgIcon icon="ph:user-circle" class="text-icon-large" />
      <span class="text-16px font-medium">{{ authStore.userInfo.userName }}</span>
    </ButtonIcon>

    <NModal v-model:show="showProfile" preset="card" :title="t('个人偏好设置', 'Profile Preferences')" style="width: 720px">
      <NSpin :show="loadingProfile">
        <NForm label-placement="top">
          <NFormItem :label="t('显示名称', 'Display Name')">
            <NInput v-model:value="profileForm.display_name" />
          </NFormItem>
          <NFormItem :label="t('简介', 'Bio')">
            <NInput v-model:value="profileForm.bio" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" />
          </NFormItem>
          <NGrid :x-gap="12" cols="2">
            <NGi>
              <NFormItem :label="t('语言', 'Language')">
                <NSelect
                  v-model:value="profileForm.preferredLanguage"
                  :options="[
                    { label: '简体中文', value: 'zh-CN' },
                    { label: 'English', value: 'en-US' }
                  ]"
                />
              </NFormItem>
            </NGi>
            <NGi>
              <NFormItem :label="t('默认模型', 'Preferred Model')">
                <NInput v-model:value="profileForm.preferredModel" placeholder="gpt-4o-mini" />
              </NFormItem>
            </NGi>
          </NGrid>

          <NDivider>{{ t('云端 API 列表', 'Cloud API List') }}</NDivider>

          <NFormItem :label="t('保存状态', 'Stored Status')">
            <NTag :type="profileForm.hasApiKey ? 'success' : 'default'" round>
              {{ profileForm.hasApiKey ? t('已在云端保存加密 Key', 'Encrypted keys stored in cloud') : t('尚未保存任何 Key', 'No key stored yet') }}
            </NTag>
          </NFormItem>

          <div v-for="(item, index) in profileForm.apiKeys" :key="`${item.secret_name}-${index}`" class="api-secret-card">
            <NGrid :x-gap="12" cols="4">
              <NGi>
                <NFormItem :label="t('API 名称', 'API Name')">
                  <NInput v-model:value="item.secret_name" :placeholder="t('例如：main-openai', 'Example: main-openai')" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem :label="t('服务商', 'Provider')">
                  <NSelect
                    v-model:value="item.provider"
                    :options="[
                      { label: 'OpenAI', value: 'openai' },
                      { label: 'Azure OpenAI', value: 'azure-openai' },
                      { label: 'Custom', value: 'custom' }
                    ]"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem :label="t('优先级', 'Priority')">
                  <NInputNumber v-model:value="item.priority" :min="1" class="w-full" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem :label="t('默认使用', 'Default Use')">
                  <NSwitch :value="profileForm.defaultApiName === item.secret_name" @update:value="() => (profileForm.defaultApiName = item.secret_name)" />
                </NFormItem>
              </NGi>
            </NGrid>
            <NGrid :x-gap="12" cols="3">
              <NGi :span="2">
                <NFormItem :label="t('请求前缀 / Endpoint', 'Request Prefix / Endpoint')">
                  <NInput
                    v-model:value="item.request_prefix"
                    :placeholder="t('例如：https://api.openai.com/v1/chat/completions', 'Example: https://api.openai.com/v1/chat/completions')"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem :label="t('API Key', 'API Key')">
                  <NInput
                    v-model:value="item.api_key"
                    type="password"
                    show-password-on="click"
                    :placeholder="t('留空表示继续沿用已保存密钥', 'Leave blank to keep the stored key')"
                  />
                </NFormItem>
              </NGi>
            </NGrid>
            <div class="api-secret-actions">
              <NButton text type="error" @click="removeApiKeyRow(index)">{{ t('删除', 'Remove') }}</NButton>
            </div>
          </div>

          <NButton dashed block @click="addApiKeyRow">{{ t('新增 API 配置', 'Add API Configuration') }}</NButton>

          <NAlert type="info" :show-icon="false">
            {{ t('API Key 会通过已认证请求传输，并在后端加密存储。后续未指定 API 名称时，系统会按优先级选择可用配置。', 'API keys are sent through authenticated requests and stored encrypted on the backend. When no API name is specified later, the system uses the highest-priority active configuration.') }}
          </NAlert>

          <div class="modal-actions">
            <NButton @click="showProfile = false">{{ t('关闭', 'Close') }}</NButton>
            <NButton tertiary @click="logout">{{ t('退出登录', 'Logout') }}</NButton>
            <NButton type="primary" :loading="saving" @click="saveProfile">{{ t('保存', 'Save') }}</NButton>
          </div>
        </NForm>
      </NSpin>
    </NModal>
  </div>
</template>

<style scoped>
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.api-secret-card {
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.72);
}

.api-secret-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
