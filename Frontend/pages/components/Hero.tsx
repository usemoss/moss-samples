import React from "react";

const Hero = () => {
  return (
    <section className="relative h-screen bg-white dark:bg-gray-900 overflow-hidden">
      {/* Animated gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-pink-50 via-white to-purple-50 dark:from-gray-900 dark:via-fuchsia-950 dark:to-gray-900">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-fuchsia-200/30 via-transparent to-transparent dark:from-fuchsia-500/20" />
      </div>

      {/* Content */}
      <div className="relative h-full px-8 lg:px-32 flex flex-col justify-center items-center text-center">
        <div className="max-w-5xl">
          {/* Logo/Brand */}
          <div className="mb-8">
            <h1 className="text-8xl lg:text-9xl font-extrabold tracking-tight">
              <span className="bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 dark:from-pink-400 dark:via-fuchsia-400 dark:to-purple-400 bg-clip-text text-transparent">
                Moss
              </span>
            </h1>
          </div>

          {/* Tagline */}
          <h2 className="text-3xl lg:text-5xl font-bold text-gray-900 dark:text-white mb-6 tracking-tight">
            Semantic Search,
            <br />
            <span className="bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 dark:from-pink-400 dark:via-fuchsia-400 dark:to-purple-400 bg-clip-text text-transparent">
              Powered by Intelligence
            </span>
          </h2>

          {/* Description */}
          <p className="text-xl lg:text-2xl text-gray-600 dark:text-gray-300 mb-12 max-w-2xl mx-auto leading-relaxed">
            Transform your data into insights with cutting-edge semantic search technology. 
            Built for developers, designed for performance.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-wrap gap-4 justify-center">
            <a 
              href="#About" 
              className="group relative inline-flex items-center justify-center px-8 py-4 text-lg font-semibold text-white transition-all duration-200 rounded-xl overflow-hidden"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 group-hover:scale-105 transition-transform duration-200" />
              <span className="relative">Get Started</span>
            </a>
            
            <a 
              href="#Projects" 
              className="group relative inline-flex items-center justify-center px-8 py-4 text-lg font-semibold text-fuchsia-600 dark:text-fuchsia-400 transition-all duration-200 rounded-xl border-2 border-fuchsia-600 dark:border-fuchsia-400 hover:bg-fuchsia-50 dark:hover:bg-fuchsia-950/30"
            >
              <span className="relative">View Projects</span>
            </a>
          </div>
        </div>
      </div>

      {/* Decorative elements */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-fuchsia-500/50 to-transparent" />
    </section>
  );
};

export default Hero;