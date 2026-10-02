<script setup lang="ts">
/**
 * V1.8 积分商城：在售商品网格 + 兑换（扣分确认）+ 我的兑换记录。
 * V1.15 装扮商品分区：头衔/徽章/头像框/气泡/特效各区展示 + 已拥有标识 + 兑换后佩戴引导。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { get, post, ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

interface Product {
  id: number
  name: string
  description: string
  price: number
  stock: number
  image_url: string | null
  type: number
  category?: number
  payload?: string
}

interface ExchangeItem {
  id: number
  product_id: number
  product_name: string
  cost: number
  status: number
  created_at: string
}

interface Page<T> {
  total: number
  items: T[]
}

const auth = useAuthStore()
const tab = ref<'products' | 'records'>('products')
const products = ref<Page<Product> | null>(null)
const records = ref<Page<ExchangeItem> | null>(null)
const loading = ref(false)
const exchanging = ref(false)

// V1.15 我的背包（已拥有的装扮商品）
const ownedIds = ref<Set<number>>(new Set())

// 装扮品类名（category 0 = 非装扮）
const CATEGORY_NAMES: Record<number, string> = {
  1: '头衔',
  2: '徽章',
  3: '头像框',
  4: '气泡',
  5: '特效',
  6: '字体',
  7: '皮肤',
  8: '宠物',
}

async function fetchProducts() {
  loading.value = true
  try {
    products.value = await get<Page<Product>>('/mall/products', { page_size: 50 })
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function fetchOwned() {
  if (!auth.isLogged) return
  try {
    const r = await get<{ items: { product_id: number }[] }>('/account/items')
    ownedIds.value = new Set(r.items.map((i) => i.product_id))
  } catch {
    // 拦截器已提示
  }
}

// 在售商品分区：装扮各区（有货的品类） + 其他（实物/非装扮）
const decorSections = computed(() => {
  const all = products.value?.items ?? []
  const sections: { category: number; label: string; items: Product[] }[] = []
  for (const [cat, label] of Object.entries(CATEGORY_NAMES)) {
    const items = all.filter((p) => p.category === Number(cat))
    if (items.length) sections.push({ category: Number(cat), label, items })
  }
  return sections
})

const otherProducts = computed(() =>
  (products.value?.items ?? []).filter((p) => !p.category),
)

// 展示顺序：装扮各区 + 其他（实物/非装扮）
const allSections = computed(() => {
  const sections = [...decorSections.value]
  if (otherProducts.value.length) {
    sections.push({ category: 0, label: '实物好礼', items: otherProducts.value })
  }
  return sections
})

async function fetchRecords() {
  if (!auth.isLogged) return
  loading.value = true
  try {
    records.value = await get<Page<ExchangeItem>>('/mall/exchanges')
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function onTabChange(t: string | number) {
  if (t === 'records') fetchRecords()
}

function stockText(p: Product) {
  if (p.stock === -1) return '不限量'
  return p.stock > 0 ? `剩 ${p.stock} 件` : '已兑完'
}

async function onExchange(p: Product) {
  if (!auth.isLogged) {
    ElMessage.warning('请先登录')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认用 ${p.price} 积分兑换「${p.name}」？`,
      '兑换确认',
      { confirmButtonText: '确认兑换', cancelButtonText: '再想想', type: 'info' },
    )
  } catch {
    return // 取消
  }
  exchanging.value = true
  try {
    const r = await post<{ exchange_id: number }>('/mall/exchange', { product_id: p.id })
    ElMessage.success(
      p.type === 1
        ? '兑换成功！可在「个人主页 → 个性装扮」中佩戴'
        : `兑换成功（订单号 ${r.exchange_id}）`,
    )
    await auth.fetchMe() // 刷新顶栏余额
    fetchProducts() // 刷新库存
    fetchOwned() // 刷新已拥有标识
    if (tab.value === 'records') fetchRecords()
  } catch (e) {
    if (e instanceof ApiError) ElMessage.error(e.message)
  } finally {
    exchanging.value = false
  }
}

onMounted(() => {
  fetchProducts()
  fetchOwned()
  if (auth.isLogged) fetchRecords()
})
</script>

<template>
  <div class="cx-card mall">
    <div class="head-row">
      <h2>积分商城</h2>
      <el-tag v-if="auth.isLogged" type="warning" effect="light" size="large" round>
        我的积分：{{ auth.user?.credit_balance ?? 0 }}
      </el-tag>
    </div>

    <el-tabs v-model="tab" @tab-change="onTabChange">
      <el-tab-pane label="在售商品" name="products">
        <div v-loading="loading" class="sections">
          <template v-if="products?.items.length">
            <!-- V1.15 装扮分区：头衔/徽章/头像框/气泡/特效…（有货品类） + 其他 -->
            <div
              v-for="sec in allSections"
              :key="sec.category"
              class="section"
            >
              <h4 class="sec-title">{{ sec.label }}</h4>
              <div class="grid">
                <div v-for="p in sec.items" :key="p.id" class="card">
                  <div class="thumb">
                    <img v-if="p.image_url" :src="p.image_url" :alt="p.name" />
                    <span
                      v-else-if="p.category === 2 && p.payload"
                      class="thumb-emoji"
                    >{{ p.payload }}</span>
                    <span v-else-if="p.category === 1 && p.payload" class="thumb-title">{{ p.payload }}</span>
                    <span v-else class="thumb-fallback">{{ p.name.slice(0, 1) }}</span>
                  </div>
                  <div class="info">
                    <div class="name-row">
                      <span class="name">{{ p.name }}</span>
                      <el-tag v-if="ownedIds.has(p.id)" size="small" type="success" effect="plain">
                        已拥有
                      </el-tag>
                      <el-tag v-else size="small" :type="p.type === 1 ? 'success' : 'warning'">
                        {{ p.type === 1 ? '虚拟权益' : '实物' }}
                      </el-tag>
                    </div>
                    <p class="desc">{{ p.description }}</p>
                    <div class="bottom">
                      <span class="price">{{ p.price }} 积分</span>
                      <span class="stock" :class="{ out: p.stock !== -1 && p.stock <= 0 }">
                        {{ stockText(p) }}
                      </span>
                      <el-button
                        type="primary"
                        size="small"
                        round
                        :disabled="ownedIds.has(p.id) || (p.stock !== -1 && p.stock <= 0)"
                        :loading="exchanging"
                        @click="onExchange(p)"
                      >
                        {{ ownedIds.has(p.id) ? '已拥有' : '兑换' }}
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <el-empty v-else-if="!loading" description="商城暂无在售商品" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="我的兑换" name="records">
        <div v-loading="loading" class="records">
          <template v-if="records?.items.length">
            <div v-for="r in records.items" :key="r.id" class="record">
              <span class="r-name">{{ r.product_name }}</span>
              <el-tag size="small" :type="r.status === 2 ? 'success' : 'info'">
                {{ r.status === 2 ? '已完成' : '待发货' }}
              </el-tag>
              <span class="r-time">{{ (r.created_at || '').replace('T', ' ').slice(0, 16) }}</span>
              <span class="r-cost">-{{ r.cost }} 积分</span>
            </div>
          </template>
          <el-empty v-else-if="!loading && auth.isLogged" description="还没有兑换记录" />
          <el-empty v-else-if="!loading" description="登录后可查看兑换记录" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.mall {
  padding: 20px 24px 24px;
}

.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.head-row h2 {
  margin: 0;
  font-size: 18px;
}

/* V1.15 分区 */
.sections {
  min-height: 200px;
}

.section + .section {
  margin-top: 24px;
}

.sec-title {
  margin: 12px 0 10px;
  font-size: 15px;
  color: #333;
  border-left: 3px solid var(--el-color-primary);
  padding-left: 8px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s;
}

.card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.thumb {
  height: 110px;
  background: var(--el-color-primary-light-9);
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-fallback {
  font-size: 40px;
  font-weight: 700;
  color: var(--el-color-primary-light-5);
}

/* V1.15 装扮商品缩略图预览：徽章 emoji / 头衔文本 */
.thumb-emoji {
  font-size: 44px;
}

.thumb-title {
  padding: 2px 10px;
  border-radius: 4px;
  background: linear-gradient(135deg, #8e6df0, #b8a5ff);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}

.info {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.name {
  font-weight: 600;
  font-size: 15px;
}

.desc {
  margin: 0;
  color: #999;
  font-size: 12px;
  min-height: 32px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.bottom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}

.price {
  color: #f5a623;
  font-weight: 700;
  font-size: 15px;
}

.stock {
  color: #999;
  font-size: 12px;
  flex: 1;
}

.stock.out {
  color: var(--el-color-danger);
}

.records {
  min-height: 160px;
  padding-top: 8px;
}

.record {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 14px;
}

.r-name {
  font-weight: 600;
}

.r-time {
  color: #999;
  font-size: 12px;
  flex: 1;
}

.r-cost {
  color: #f5a623;
  font-weight: 600;
}
</style>
