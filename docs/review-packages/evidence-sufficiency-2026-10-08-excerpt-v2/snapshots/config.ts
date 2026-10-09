export const SITE = {
  name: 'NovaCNC Machinery',
  legalName: 'NovaCNC Machinery Co., Ltd.',
  description: 'A fictional demonstration CNC machinery brand used for industrial product presentation and controlled web visibility research.',
  email: 'sales@novacnc.example'
} as const;

export const NAV_ITEMS = [
  { label: 'Home', href: '/' },
  { label: 'Products', href: '/products' },
  { label: 'Solutions', href: '/solutions' },
  { label: 'Industries', href: '/industries' },
  { label: 'About', href: '/about' },
  { label: 'Blog', href: '/blog' },
  { label: 'Contact', href: '/contact' }
] as const;

export const INDEXABLE_ROUTES = [
  '/',
  '/about',
  '/products',
  '/products/cnc-milling-machine',
  '/products/cnc-lathe',
  '/products/cnc-machining-center',
  '/products/fiber-laser-cutting-machine',
  '/solutions',
  '/industries',
  '/blog',
  '/blog/how-to-choose-a-cnc-machine',
  '/blog/cnc-milling-vs-cnc-turning',
  '/contact'
] as const;
