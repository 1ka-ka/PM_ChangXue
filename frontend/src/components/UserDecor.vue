<script setup lang="ts">
/**
 * V1.15 用户装扮装饰件：昵称旁的头衔标签 + 徽章 emoji。
 * 数据来自后端 brief()/author_equipped 佩戴快照：{slot: {product_id, name, payload}}。
 */
interface EquipSlot {
  product_id: number
  name: string
  payload: string
}

interface Equipped {
  title?: EquipSlot
  badge?: EquipSlot
  [key: string]: EquipSlot | undefined
}

const props = defineProps<{ equipped?: Equipped | null }>()

function titleText(t?: EquipSlot) {
  return t?.payload || t?.name || ''
}
</script>

<template>
  <span v-if="props.equipped?.title || props.equipped?.badge" class="user-decor">
    <span v-if="props.equipped?.title" class="decor-title">{{ titleText(props.equipped.title) }}</span>
    <span v-if="props.equipped?.badge" class="decor-badge" :title="props.equipped.badge.name">
      {{ props.equipped.badge.payload }}
    </span>
  </span>
</template>

<style scoped>
.user-decor {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  vertical-align: middle;
}

.decor-title {
  display: inline-block;
  padding: 0 6px;
  border-radius: 4px;
  background: linear-gradient(135deg, #8e6df0, #b8a5ff);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 17px;
  white-space: nowrap;
}

.decor-badge {
  font-size: 13px;
  line-height: 1;
  cursor: default;
}
</style>
