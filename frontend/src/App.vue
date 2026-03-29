<script setup>

</script>

<template>
  <router-view></router-view>
</template>

<style lang="scss">
@use '@/styles/variables.scss';
@use '@/styles/common.scss';
@use '@/styles/transitions.scss';

* {
  font-family:
    ui-sans-serif,
    -apple-system,
    system-ui,
    Segoe UI,
    Helvetica,
    Apple Color Emoji,
    Arial,
    sans-serif,
    Segoe UI Emoji,
    Segoe UI Symbol;
}

html,
body {
  transition: background-color 0.3s ease, color 0.3s ease;
}

html {
  color-scheme: light;
}

[data-theme='dark'] {
  color-scheme: dark;
}

html,
body,
#app {
  background: var(--color-bg-base);
}

* {
  scrollbar-width: thin;
  scrollbar-color: var(--color-scrollbar-thumb) var(--color-scrollbar-track);
}

*::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

*::-webkit-scrollbar-track {
  background: var(--color-scrollbar-track);
}

*::-webkit-scrollbar-thumb {
  background: var(--color-scrollbar-thumb);
  border-radius: 999px;
  border: 2px solid var(--color-scrollbar-track);
}

*::-webkit-scrollbar-thumb:hover {
  background: var(--color-scrollbar-thumb-hover);
}

*::-webkit-scrollbar-corner {
  background: var(--color-scrollbar-track);
}
</style>
