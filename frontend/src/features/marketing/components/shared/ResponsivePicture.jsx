export default function ResponsivePicture({ webpSrc, fallbackSrc, alt, width, height, loading = 'lazy', fetchPriority, className = '' }) {
  return (
    <picture className={className}>
      <source srcSet={webpSrc} type="image/webp" />
      <img src={fallbackSrc} alt={alt} width={width} height={height} loading={loading} fetchPriority={fetchPriority} decoding="async" />
    </picture>
  )
}
