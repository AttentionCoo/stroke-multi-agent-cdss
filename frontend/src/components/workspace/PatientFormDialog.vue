<script setup>
defineOptions({ name: 'PatientFormDialog' })

defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  mode: {
    type: String,
    default: 'create',
  },
})

const form = defineModel('form', { required: true })

const emit = defineEmits(['close', 'submit'])
</script>

<template>
  <div v-if="visible" class="dialog-overlay" @click.self="emit('close')">
    <div class="dialog-card" @click.stop>
      <div class="dialog-head">
        <div>
          <p class="summary-label">患者信息</p>
          <h3>{{ mode === 'edit' ? '编辑患者' : '新增患者' }}</h3>
        </div>
        <button type="button" class="ghost-icon" @click="emit('close')">✕</button>
      </div>

      <div class="dialog-body form-stack">
        <label class="field-label">
          姓名
          <input v-model="form.name" type="text" placeholder="请输入患者姓名" />
        </label>
        <label class="field-label">
          病史
          <textarea v-model="form.history" rows="5" placeholder="请输入既往病史或慢性病信息"></textarea>
        </label>
        <label class="field-label">
          医生备注
          <textarea v-model="form.notes" rows="5" placeholder="请输入医嘱、随访或注意事项"></textarea>
        </label>
      </div>

      <div class="dialog-footer">
        <button type="button" class="secondary-action" @click="emit('close')">取消</button>
        <button type="button" class="primary-action" @click="emit('submit')">保存</button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 31, 37, 0.34);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 110;
  padding: 20px;
}

.dialog-card {
  width: min(720px, 100%);
  max-height: min(84vh, 900px);
  overflow: auto;
  border-radius: 28px;
  border: 1px solid rgba(217, 230, 226, 0.95);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 20px 45px rgba(15, 65, 79, 0.12);
  padding: 22px;
}

.dialog-head,
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dialog-head h3,
.summary-label {
  margin: 0;
}

.summary-label {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #2c7c6e;
}

.ghost-icon,
.primary-action,
.secondary-action {
  border: none;
  cursor: pointer;
  transition: all 0.18s ease;
}

.ghost-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgba(236, 245, 243, 0.82);
  color: #5e7379;
}

.primary-action,
.secondary-action {
  padding: 11px 16px;
  border-radius: 14px;
  font-weight: 700;
}

.primary-action {
  background: linear-gradient(135deg, #11967f 0%, #0f7666 100%);
  color: #ffffff;
}

.secondary-action {
  background: rgba(230, 241, 238, 0.9);
  color: #17313a;
}

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 18px;
}

.field-label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-weight: 700;
  color: #17313a;
}

.field-label input,
.field-label textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(191, 213, 207, 0.95);
  background: rgba(249, 252, 252, 0.96);
  border-radius: 14px;
  padding: 12px 14px;
  font: inherit;
  color: #17313a;
}

.field-label textarea {
  resize: vertical;
}

.dialog-footer {
  margin-top: 18px;
  justify-content: flex-end;
}


@media (max-width: 640px) {

  .dialog-head,
  .dialog-footer {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>