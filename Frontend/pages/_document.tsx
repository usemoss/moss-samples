import { Html, Head, Main, NextScript } from 'next/document'

export default function Document() {
  return (
    <Html lang="en" className='scroll-smooth'>
      <Head>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.15.1/devicon.min.css"/>
      </Head>
      <body className='text-gray-900 dark:text-gray-100 bg-white dark:bg-zinc-950 transition-colors duration-300'>
        <Main />
        <NextScript />
      </body>
    </Html>
  )
}
