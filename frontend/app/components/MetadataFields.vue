<template>
  <div v-if="schema.length" class="grid gap-4 sm:grid-cols-2">
    <UFormField
      v-for="field in schema"
      :key="field.key"
      :name="field.key"
      :label="field.label"
      :required="field.required"
      :help="field.help || field.description"
    >
      <USelectMenu
        v-if="(field.type === 'select' || field.type === 'multiselect') && !field.allowCustom"
        :model-value="getValue(field)"
        @update:model-value="(v) => setValue(field, v)"
        :multiple="field.type === 'multiselect'"
        :items="selectOptions(field)"
        :aria-label="field.label"
        :placeholder="field.placeholder || 'Select an option'"
        value-key="value"
        class="w-full"
      />

      <template v-else-if="field.type === 'select' || field.type === 'multiselect'">
        <UInput
          :model-value="displayCustom(field)"
          @update:model-value="(v) => setCustom(field, v as string)"
          :list="field.options?.length ? `${id}-${field.key}` : undefined"
          :placeholder="field.placeholder"
          class="w-full"
        />
        <datalist v-if="field.options?.length" :id="`${id}-${field.key}`">
          <option v-for="opt in selectOptions(field)" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </datalist>
      </template>

      <UTextarea
        v-else-if="field.type === 'text'"
        :model-value="getValue(field)"
        @update:model-value="(v) => setValue(field, v)"
        :placeholder="field.placeholder"
        class="w-full"
      />

      <USwitch
        v-else-if="field.type === 'boolean'"
        :model-value="getValue(field)"
        @update:model-value="(v) => setValue(field, v)"
        class="w-full"
      />

      <UInput
        v-else
        :model-value="getValue(field)"
        @update:model-value="(v) => setValue(field, v)"
        v-bind="inputProps(field)"
        class="w-full"
      />
    </UFormField>
  </div>
</template>

<script setup lang="ts">
import type { Field } from '../types/metadata';
import { useId } from 'vue';
import { UInput, UTextarea, USwitch, USelectMenu } from '#components';

const { schema } = defineProps<{ schema: Field[] }>();
const id = useId();

const modelValue = defineModel<Record<string, any>>({ required: true });
const emit = defineEmits<{ change: [Record<string, any>] }>();

function setValue(field: Field, value: any) {
  modelValue.value = { ...modelValue.value, [field.key]: value };
  emit('change', modelValue.value);
}

function getValue(field: Field) {
  return modelValue.value?.[field.key];
}

function displayCustom(field: Field): string {
  const val = getValue(field);
  if (field.type === 'multiselect') {
    return Array.isArray(val) ? val.join(', ') : '';
  }
  return val ?? '';
}

function setCustom(field: Field, v: string) {
  if (field.type === 'multiselect') {
    const arr = v
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    setValue(field, arr);
  } else {
    setValue(field, v);
  }
}

function inputProps(field: Field) {
  const base: Record<string, any> = {
    placeholder: field.placeholder,
  };
  if (field.type === 'date') base.type = 'date';
  if (field.type === 'datetime') base.type = 'datetime-local';
  if (field.type === 'number' || field.type === 'integer') {
    base.type = 'number';
    if (field.min !== undefined) base.min = field.min;
    if (field.max !== undefined) base.max = field.max;
    base.step = field.type === 'integer' ? 1 : 'any';
  }
  if (field.type === 'string' || field.type === 'text') {
    if (field.minLength) base.minlength = field.minLength;
    if (field.maxLength) base.maxlength = field.maxLength;
    if (field.regex) base.pattern = field.regex;
  }
  return base;
}

function selectOptions(field: Field) {
  return (field.options || []).map((o) => (typeof o === 'string' ? { label: o, value: o } : o));
}
</script>
