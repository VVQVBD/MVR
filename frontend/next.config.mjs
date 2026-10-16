/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keeps a production build independent from an active `next dev` session.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
export default nextConfig;
