import type { AppProps } from 'next/app'
import { Inter } from 'next/font/google'
import 'nextra-theme-docs/style.css'
import '../styles/globals.css'

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
})

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={`${inter.variable} ${inter.className}`}>
      <Component {...pageProps} />
    </div>
  )
}
