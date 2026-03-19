<template>
  <div class="__debug-panel" v-if="show && !collapsed" @click.stop>
    <div class="__debug-header">Debug
      <button class="dbg-toggle" @click.stop="collapsed = true">▁</button>
    </div>
    <div class="__debug-body">
      <div style="display:flex;gap:6px;flex-direction:column">
        <textarea v-model="pyCodeLocal" rows="4" class="pycode-textarea" style="width:100%;border-radius:6px;padding:6px;font-family:monospace"></textarea>
        <div style="display:flex;gap:8px;align-items:center">
          <n-button size="small" @click="$emit('runPy', pyCodeLocal)">Run Py</n-button>
          <div style="color:var(--n-text-2);font-size:12px">Pyodide: <b>{{ pyReady ? 'ready' : 'loading' }}</b></div>
        </div>
        <div style="height:6px"></div>
        <div style="display:flex;gap:8px;align-items:center">
          <input placeholder="comma separated packages or wheel URLs" v-model="pyPackagesLocal" style="flex:1;padding:6px;border-radius:6px;border:1px solid rgba(0,0,0,0.06)" />
          <n-button size="small" @click="$emit('install', pyPackagesLocal)">Install</n-button>
        </div>
      </div>
      <div style="height:8px"></div>
      <div v-for="(l, i) in logs" :key="i" class="__debug-line">{{ l }}</div>
    </div>
  </div>

  <div v-if="show && collapsed" class="__debug-mini" @click.stop="collapsed = false">D</div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
const props = defineProps<{ show: boolean; pyReady: boolean; pyCode: string; pyPackages: string; logs: string[] }>();
const emit = defineEmits(['runPy', 'install']);
const pyCodeLocal = ref(props.pyCode || '');
const pyPackagesLocal = ref(props.pyPackages || '');
const collapsed = ref(false);
watch(() => props.pyCode, v => pyCodeLocal.value = v || '');
watch(() => props.pyPackages, v => pyPackagesLocal.value = v || '');
</script>

<style scoped>
.__debug-panel { position: fixed; left: 12px; bottom: 12px; width:320px; max-height:40vh; background: rgba(20,20,20,0.85); color: #e6eef9; font-size:12px; border-radius:8px; overflow:hidden; z-index:99999; box-shadow:0 8px 30px rgba(0,0,0,0.4); }
.__debug-header { padding:6px 8px; border-bottom:1px solid rgba(255, 255, 255, 0.359); font-weight:700 }
.__debug-body { padding:6px 8px; overflow:auto; max-height:calc(40vh - 36px) }
.__debug-line { padding:2px 0; white-space:pre-wrap; word-break:break-word; opacity:0.9 }
.n_button { color: #e6eef9 };
/* Ensure python textarea and package input have white text by default */
.__debug-body textarea,
.__debug-body input {
  color: #ffffff;
  background-color: transparent;
}
/* Make the main pyodide code textarea green */
.__debug-body textarea.pycode-textarea {
  color: #5eea5e !important;
}
/* Naive UI buttons: force white text inside the debug panel */
.__debug-body .n-button,
.__debug-body .n-button * {
  color: #ffffff !important;
}
.dbg-toggle { float:right; background:transparent; border:0; color:#e6eef9; cursor:pointer; font-size:12px; padding:4px; margin-left:8px }
.dbg-toggle:focus { outline: none }
.__debug-mini { position: fixed; left: 12px; bottom: 12px; width:40px; height:40px; border-radius:8px; background: rgba(20,20,20,0.85); color:#e6eef9; display:flex; align-items:center; justify-content:center; font-weight:700; z-index:99999; box-shadow:0 8px 30px rgba(0,0,0,0.4); cursor:pointer }
</style>