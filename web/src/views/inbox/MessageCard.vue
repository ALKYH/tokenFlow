<script setup lang="ts">
const props = defineProps<{ message: any; selected: boolean }>()
const emit = defineEmits<{ (e: 'open', id: any): void; (e: 'toggle', id: any): void }>()

function formatDate(ts: number) {
  try { const d = new Date(ts); return d.toLocaleString(); } catch (e) { return '' }
}
</script>

<template>
  <div class="msg-card" :class="{ selected: selected }" @click="$emit('open', message)">
    <div class="left">
      <input type="checkbox" class="sel" :checked="selected" @click.stop="$emit('toggle', message.id)" />
    </div>
    <div class="center">
      <div class="row top">
        <div class="subject">{{ message.subject }}</div>
        <div class="time">{{ formatDate(message.date) }}</div>
      </div>
      <div class="row mid">
        <div class="snippet">{{ message.snippet }}</div>
      </div>
    </div>
    <div class="right">
      <div class="badge file-type">{{ message.fileType || '—' }}</div>
      <div class="badge module">{{ message.module || '通用' }}</div>
    </div>
  </div>
</template>

<style scoped>
.msg-card { display:flex; gap:12px; align-items:flex-start; padding:10px; border-bottom:1px solid rgba(0,0,0,0.04); cursor:pointer }
.msg-card:hover { background: rgba(0,0,0,0.02) }
.msg-card.selected { background: rgba(40,116,240,0.06) }
.left { width:36px; display:flex; align-items:center; justify-content:center }
.center { flex:1; min-width:0 }
.row.top { display:flex; justify-content:space-between; align-items:center }
.subject { font-weight:600; color:var(--n-text-1,#111); overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.time { font-size:12px; color:var(--n-text-3,#888); margin-left:8px }
.snippet { color:var(--n-text-2,#555); font-size:13px; margin-top:6px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden }
.right { display:flex; flex-direction:column; gap:6px; align-items:flex-end }
.badge { padding:6px 8px; border-radius:8px; font-size:12px; background:var(--n-card-color,#f3f6ff); color:var(--n-text-1,#222) }
.file-type { background:linear-gradient(90deg,#f7f9fb,#eef6ff) }
.module { background:linear-gradient(90deg,#fff7ed,#fff1e6); color:#8a4b00 }
.sel { width:16px; height:16px }
</style>
