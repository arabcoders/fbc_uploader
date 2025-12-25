<style>
.markdown-alert {
    padding: 0 1em;
    margin-bottom: 16px;
    color: inherit;
    border-left: 0.25em solid #444c56;
}

.markdown-alert-title {
    display: inline-flex;
    align-items: center;
    font-weight: 500;
    text-transform: uppercase;
    user-select: none;
}

.markdown-alert-note {
    border-left-color: #539bf5;
}

.markdown-alert-tip {
    border-left-color: #57ab5a;
}

.markdown-alert-important {
    border-left-color: #986ee2;
}

.markdown-alert-warning {
    border-left-color: #c69026;
}

.markdown-alert-caution {
    border-left-color: #e5534b;
}

.markdown-alert-note>.markdown-alert-title {
    color: #539bf5;
}

.markdown-alert-tip>.markdown-alert-title {
    color: #57ab5a;
}

.markdown-alert-important>.markdown-alert-title {
    color: #986ee2;
}

.markdown-alert-warning>.markdown-alert-title {
    color: #c69026;
}

.markdown-alert-caution>.markdown-alert-title {
    color: #e5534b;
}
</style>

<template>
    <div v-html="transformedContent">
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { marked } from 'marked'
import { baseUrl } from 'marked-base-url'
import markedAlert from 'marked-alert'
import { gfmHeadingId } from 'marked-gfm-heading-id'

const props = defineProps<{ content: string }>()

const transformedContent = ref<string>('')

onMounted(async () => {
    marked.use(gfmHeadingId())
    marked.use(baseUrl(window.origin))
    marked.use(markedAlert())
    marked.use({ gfm: true })
    transformedContent.value = String(marked.parse(props.content))
})
</script>
