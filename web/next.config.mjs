/** @type {import('next').NextConfig} */
const nextConfig = {
  // Firebase Hosting serves this as static files; every read is client-side,
  // so there is no server to deploy.
  output: 'export',
  images: { unoptimized: true },
  trailingSlash: true,
};
export default nextConfig;
