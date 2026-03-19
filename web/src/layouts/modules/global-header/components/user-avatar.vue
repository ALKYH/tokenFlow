<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import { useRouterPush } from '@/hooks/common/router';
import { getLocale, setLocale } from '@/locales';
import { fetchMyProfile, getStoredAccessToken, updateMyProfile } from '@/service/api';

defineOptions({
  name: 'UserAvatar'
});

const authStore = useAuthStore();
const { toLogin } = useRouterPush();
const showProfile = ref(false);
const saving = ref(false);
const loadingProfile = ref(false);
const profileForm = reactive({
  display_name: '',
  bio: '',
  preferredLanguage: getLocale(),
  preferredModel: 'gpt-4o-mini',
  apiProvider: 'openai',
  apiKey: '',
  hasApiKey: false
});

function loginOrRegister() {
  toLogin();
}

async function openProfile() {
  showProfile.value = true;
  const token = getStoredAccessToken();
  profileForm.display_name = authStore.userInfo.userName || 'TokenFlow User';
  profileForm.bio = '';
  profileForm.preferredLanguage = getLocale();
  profileForm.preferredModel = 'gpt-4o-mini';
  profileForm.apiProvider = 'openai';
  profileForm.apiKey = '';
  profileForm.hasApiKey = false;

  if (!token) return;
  loadingProfile.value = true;
  try {
    const data = await fetchMyProfile(token);
    profileForm.display_name = data.display_name || profileForm.display_name;
    profileForm.bio = data.bio || '';
    profileForm.preferredLanguage = data.preferences?.preferredLanguage || getLocale();
    profileForm.preferredModel = data.preferences?.preferredModel || 'gpt-4o-mini';
    profileForm.apiProvider = data.api_provider || 'openai';
    profileForm.hasApiKey = !!data.has_api_key;
  } catch {
    window.$message?.warning('Cloud profile is unavailable, local values are shown.');
  } finally {
    loadingProfile.value = false;
  }
}

async function saveProfile() {
  const token = getStoredAccessToken();
  if (!token) {
    window.$message?.warning('Please sign in to sync profile preferences to cloud.');
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
          preferredModel: profileForm.preferredModel
        },
        api_provider: profileForm.apiProvider,
        api_key: profileForm.apiKey || undefined
      },
      token
    );
    setLocale(profileForm.preferredLanguage as App.I18n.LangType);
    profileForm.apiKey = '';
    profileForm.hasApiKey = true;
    window.$message?.success('Profile saved');
    showProfile.value = false;
  } catch {
    window.$message?.error('Profile save failed');
  } finally {
    saving.value = false;
  }
}

function logout() {
  window.$dialog?.info({
    title: 'Confirm',
    content: 'Sign out from current session?',
    positiveText: 'Logout',
    negativeText: 'Cancel',
    onPositiveClick: () => {
      authStore.resetStore();
    }
  });
}
</script>

<template>
  <NButton v-if="!authStore.isLogin" quaternary @click="loginOrRegister">Login / Register</NButton>
  <div v-else>
    <ButtonIcon @click="openProfile">
      <SvgIcon icon="ph:user-circle" class="text-icon-large" />
      <span class="text-16px font-medium">{{ authStore.userInfo.userName }}</span>
    </ButtonIcon>

    <NModal v-model:show="showProfile" preset="card" title="Profile Preferences" style="width: 560px">
      <NSpin :show="loadingProfile">
        <NForm label-placement="top">
          <NFormItem label="Display Name">
            <NInput v-model:value="profileForm.display_name" />
          </NFormItem>
          <NFormItem label="Bio">
            <NInput v-model:value="profileForm.bio" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" />
          </NFormItem>
          <NGrid :x-gap="12" :y-gap="0" cols="2">
            <NGi>
              <NFormItem label="Language">
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
              <NFormItem label="Preferred Model">
                <NInput v-model:value="profileForm.preferredModel" placeholder="gpt-4o-mini" />
              </NFormItem>
            </NGi>
          </NGrid>
          <NDivider>Cloud API Secret</NDivider>
          <NGrid :x-gap="12" cols="2">
            <NGi>
              <NFormItem label="Provider">
                <NSelect
                  v-model:value="profileForm.apiProvider"
                  :options="[
                    { label: 'OpenAI', value: 'openai' },
                    { label: 'Azure OpenAI', value: 'azure-openai' },
                    { label: 'Custom', value: 'custom' }
                  ]"
                />
              </NFormItem>
            </NGi>
            <NGi>
              <NFormItem label="Stored Status">
                <NTag :type="profileForm.hasApiKey ? 'success' : 'default'" round>
                  {{ profileForm.hasApiKey ? 'Encrypted key stored in cloud' : 'No key stored yet' }}
                </NTag>
              </NFormItem>
            </NGi>
          </NGrid>
          <NFormItem label="API Key">
            <NInput
              v-model:value="profileForm.apiKey"
              type="password"
              show-password-on="click"
              placeholder="Leave blank to keep existing encrypted key"
            />
          </NFormItem>
          <NAlert type="info" :show-icon="false">
            API keys are transmitted as authenticated requests and stored encrypted on the backend. For production, deploy the API behind HTTPS.
          </NAlert>
          <div class="modal-actions">
            <NButton @click="showProfile = false">Close</NButton>
            <NButton tertiary @click="logout">Logout</NButton>
            <NButton type="primary" :loading="saving" @click="saveProfile">Save</NButton>
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
</style>
