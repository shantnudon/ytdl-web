<script>
  let { width = '100%', height = '14px', radius = '6px', style = '' } = $props()
</script>

<span
  class="skeleton"
  aria-hidden="true"
  style={`width:${width};height:${height};border-radius:${radius};${style}`}
></span>
