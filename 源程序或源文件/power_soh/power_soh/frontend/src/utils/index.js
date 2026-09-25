// 工具函数集合

// 格式化日期
export const formatDate = (date, fmt = 'YYYY-MM-DD HH:mm:ss') => {
  if (!date) return ''
  if (typeof date === 'string') {
    date = new Date(date)
  }
  const o = {
    'M+': date.getMonth() + 1,
    'D+': date.getDate(),
    'h+': date.getHours(),
    'm+': date.getMinutes(),
    's+': date.getSeconds(),
    'q+': Math.floor((date.getMonth() + 3) / 3),
    'S': date.getMilliseconds()
  }
  if (/(Y+)/.test(fmt)) {
    fmt = fmt.replace(RegExp.$1, (date.getFullYear() + '').substr(4 - RegExp.$1.length))
  }
  for (let k in o) {
    if (new RegExp('(' + k + ')').test(fmt)) {
      fmt = fmt.replace(RegExp.$1, (RegExp.$1.length === 1) ? (o[k]) : (('00' + o[k]).substr(('' + o[k]).length)))
    }
  }
  return fmt
}

// 数字格式化
export const formatNumber = (num, decimals = 2) => {
  if (num === null || num === undefined) return '-'
  return parseFloat(num).toFixed(decimals)
}

// 下载文件
export const downloadFile = (data, filename, mime) => {
  const blob = new Blob([data], { type: mime })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

// 深拷贝
export const deepClone = (obj) => {
  if (obj === null || typeof obj !== 'object') return obj
  if (obj instanceof Date) return new Date(obj.getTime())
  if (obj instanceof Array) return obj.reduce((arr, item, i) => {
    arr[i] = deepClone(item)
    return arr
  }, [])
  if (typeof obj === 'object') {
    return Object.keys(obj).reduce((newObj, key) => {
      newObj[key] = deepClone(obj[key])
      return newObj
    }, {})
  }
}

// 防抖函数
export const debounce = (func, wait) => {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

// 节流函数
export const throttle = (func, limit) => {
  let inThrottle
  return function() {
    const args = arguments
    const context = this
    if (!inThrottle) {
      func.apply(context, args)
      inThrottle = true
      setTimeout(() => inThrottle = false, limit)
    }
  }
}