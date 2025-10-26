import React from "react";
import Image from "next/image";
import config from "../../index.json";

const TalkToYourPdf = () => {
  const data = config.sampleUseCases.talkToYourPdf;
  
  return (
    <section id="TalkToYourPdf" className="px-8 lg:px-32 py-20 bg-gray-50 dark:bg-zinc-900 transition-colors duration-300">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl lg:text-5xl font-bold text-center text-gray-900 dark:text-white mb-4">
          {data.title}
        </h1>
        <p className="text-center text-gray-600 dark:text-gray-400 mb-16 max-w-2xl mx-auto">
          {data.subtitle}
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Content */}
          <div className="space-y-6">
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              {data.subtitle}
            </h2>
            <p className="text-gray-600 dark:text-gray-400 text-lg leading-relaxed">
              {data.description}
            </p>
            
            <div className="space-y-4">
              {data.features.map((feature, index) => (
                <div key={index} className="flex items-start space-x-3">
                  <div className="w-2 h-2 bg-fuchsia-600 rounded-full mt-2"></div>
                  <p className="text-gray-600 dark:text-gray-400">
                    <strong className="text-gray-900 dark:text-white">{feature.split(':')[0]}:</strong> {feature.split(':')[1]}
                  </p>
                </div>
              ))}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-4 pt-6">
              <a 
                href={data.url} 
                target="_blank" 
                rel="noreferrer"
                className="px-6 py-3 rounded-lg bg-gradient-to-r from-pink-600 via-fuchsia-600 to-purple-600 text-white font-semibold hover:shadow-lg hover:scale-105 transition-all duration-200"
              >
                Try Demo
              </a>
              <a 
                href={data.github} 
                target="_blank" 
                rel="noreferrer"
                className="px-6 py-3 rounded-lg border-2 border-fuchsia-600 dark:border-fuchsia-400 text-fuchsia-600 dark:text-fuchsia-400 font-semibold hover:bg-fuchsia-50 dark:hover:bg-fuchsia-950/30 transition-all duration-200"
              >
                View Code
              </a>
            </div>
          </div>

          {/* Image */}
          <div className="relative h-96 rounded-2xl overflow-hidden shadow-lg">
            <Image 
              src={data.image} 
              alt={data.title}
              className="w-full h-full object-cover" 
              width={700} 
              height={350}
            />
          </div>
        </div>
      </div>
    </section>
  );
};

export default TalkToYourPdf;