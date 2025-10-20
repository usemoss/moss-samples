import React from "react";
import config from "../index.json";
import Image from "next/image";

const Projects = () => {
  const projects = config.projects;
  return (
    <section id="Sample Usecase" className="px-8 lg:px-32 py-20 bg-white dark:bg-zinc-950 transition-colors duration-300">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl lg:text-5xl font-bold text-center text-gray-900 dark:text-white mb-4">
          {projects.title}
        </h1>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-16 max-w-2xl mx-auto">
          Explore real-world applications and implementations
        </p>

        {/* Grid Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {projects.projects.map((item) => (
            <div 
              key={item.title} 
              className="group bg-white dark:bg-zinc-900 rounded-2xl overflow-hidden shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-200 dark:border-zinc-800 hover:scale-105"
            >
              {/* Image */}
              <div className="relative h-48 overflow-hidden">
                <Image 
                  src={item.image} 
                  alt={item.title}
                  className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300" 
                  width={700} 
                  height={350}
                />
              </div>

              {/* Content */}
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                  {item.title}
                </h2>
                <p className="text-gray-600 dark:text-gray-400 mb-6 line-clamp-3">
                  {item.description}
                </p>

                {/* Action Buttons */}
                <div className="flex gap-3">
                  <a 
                    href={item.url} 
                    target="_blank" 
                    rel="noreferrer"
                    className="flex-1 text-center px-4 py-2.5 rounded-lg bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 text-white font-semibold hover:shadow-lg hover:scale-105 transition-all duration-200"
                  >
                    View Demo
                  </a>
                  <a 
                    href={item.github} 
                    target="_blank" 
                    rel="noreferrer"
                    className="px-4 py-2.5 rounded-lg border-2 border-fuchsia-600 dark:border-fuchsia-400 text-fuchsia-600 dark:text-fuchsia-400 font-semibold hover:bg-fuchsia-50 dark:hover:bg-fuchsia-950/30 transition-all duration-200"
                  >
                    Code
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Projects;