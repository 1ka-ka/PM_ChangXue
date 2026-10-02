<script setup lang="ts">
/**
 * V1.15 装扮头像：根据佩戴快照渲染头像框（frame 槽位 payload = 样式 key）。
 * 未佩戴头像框时与普通 el-avatar 一致。
 */
interface EquipSlot {
  product_id: number
  name: string
  payload: string
}

interface Equipped {
  frame?: EquipSlot
  [key: string]: EquipSlot | undefined
}

const props = defineProps<{
  size: number
  src?: string | null
  name?: string
  equipped?: Equipped | null
}>()

const emit = defineEmits<{ click: [] }>()

const frameKey = () => (props.equipped?.frame?.payload ? `frame-${props.equipped.frame.payload}` : '')
</script>

<template>
  <span class="decor-avatar" :class="frameKey()" :style="{ width: `${size}px`, height: `${size}px` }">
    <el-avatar
      :size="size - 6"
      :src="src || undefined"
      @click="emit('click')"
    >
      {{ name?.slice(0, 1) }}
    </el-avatar>
  </span>
</template>

<style scoped>
.decor-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
}

/* 头像框：环形渐变（样式 key 见商城商品 payload） */
.frame-gold {
  background: conic-gradient(#f7d774, #e8a33d, #fff3c4, #e8a33d, #f7d774);
}

.frame-silver {
  background: conic-gradient(#e8e8e8, #b0b6bf, #ffffff, #b0b6bf, #e8e8e8);
}

.frame-blue {
  background: conic-gradient(#7cc0ff, #2f7bd9, #cde8ff, #2f7bd9, #7cc0ff);
}

.frame-rose {
  background: conic-gradient(#ffb3c8, #e8547f, #ffe0ea, #e8547f, #ffb3c8);
}
</style>
