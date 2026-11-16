// Image files imported from the source (Vite turns them into URLs).
declare module "*.png" {
  const url: string;
  export default url;
}
