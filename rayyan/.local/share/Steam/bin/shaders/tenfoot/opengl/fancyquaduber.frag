//#define USEYUVSRGB 1

uniform sampler2D Texture0;
uniform sampler2D Texture1;
uniform sampler2D Texture2;
uniform sampler1D Texture3;

uniform vec4 outercornerradii0;
uniform vec4 outercornerradii1;
uniform vec4 innercornerradii0;
uniform vec4 innercornerradii1;
uniform vec4 bordercolor;
uniform vec4 gradientradialoffset;

varying vec4 texcoordgradientcoord;// texcoord and position in gradient space (where length()=0 is color0, length()=1 is color1, values in between predictably linear interpolate, values outside are clamped)
varying vec4 outercornercoord0; // coords in the rounded corner space for top left and top right
varying vec4 outercornercoord1; // coords in the rounded corner space for bottom left and bottom right
varying vec4 innercornercoord0; // coords in the rounded corner space for top left and top right
varying vec4 innercornercoord1; // coords in the rounded corner space for bottom left and bottom right
varying vec4 color0; // gradient start color (stop position = 0.0)
varying vec4 color1; // gradient end color (stop position = 1.0)
varying vec4 opacitytexcoord; // texcoord for opacitymask

#ifdef USEDESATURATION
uniform float g_Desaturation;
const vec3 coef = vec3(0.3, 0.59, 0.11);
#endif

#ifdef USEOPACITYMASK
uniform float g_OpacityMaskOpacity;
#endif

void main (void)
{
#ifdef TEXTURETYPE_RGBA
	vec4 texcol = texture2D( Texture0, texcoordgradientcoord.st );
#elif defined(TEXTURETYPE_PREMUL)
	vec4 texcol = texture2D( Texture0, texcoordgradientcoord.st );
	texcol.rgb *= texcol.a;
#elif defined(TEXTURETYPE_ALPHA)
	vec4 texcol = texture2D( Texture0, texcoordgradientcoord.st ).a * vec4(1.0, 1.0, 1.0, 1.0);
#elif defined(TEXTURETYPE_YUV)
	// direct decoding of YV12 or I420 video
	float y = texture2D( Texture0, texcoordgradientcoord.st ).r;
	float u = texture2D( Texture1, texcoordgradientcoord.st ).r;
	float v = texture2D( Texture2, texcoordgradientcoord.st ).r;

	y = 1.1643*(y-0.0625);
	u = u-0.5;
	v = v-0.5;

	vec4 texcol = vec4(y+1.5958*v, y-0.39173*u-0.81290*v, y+2.017*u, 1.0);
#ifdef USEYUVSRGB
	texcol.r = pow(texcol.r, 2.2);
	texcol.g = pow(texcol.g, 2.2);
	texcol.b = pow(texcol.b, 2.2);
#endif
#else
	vec4 texcol = vec4(1.0, 1.0, 1.0, 1.0);
#endif

#ifdef USEDESATURATION
	// Desaturate colors if needed
	texcol.rgb = mix( texcol.rgb, dot( coef.rgb, texcol.rgb ) * vec3( 1.0, 1.0, 1.0 ), g_Desaturation );
#endif

#ifdef USERADIALGRADIENT
	// more complex math needed for off-center radial
#if 0
	float gradientposition = length(texcoordgradientcoord.zw);
#else
	float cdx = gradientradialoffset.x;
	float cdy = gradientradialoffset.y;
	float dr = 1.0 - 0.0;
	float A = cdx * cdx + cdy * cdy - dr * dr;
	float r1 = 0.0;
	float pdx = texcoordgradientcoord.z;
	float pdy = texcoordgradientcoord.w;
	float B = -2 * (pdx * cdx + pdy * cdy + r1 * dr);
	float C = pdx * pdx + pdy * pdy - r1 * r1;
	float det = max(B * B - 4 * A * C, 0.0f);
	float gradientposition = (-B + sign(dr * A) * sqrt(det)) / (2 * A);
	// apply scale/bias to the floating part and reassemble
//	float texFrac = frac(gradientposition) * texScale + texBias;
//	gradientposition = floor(gradientposition) + texFrac;
#endif
#else
	float gradientposition = texcoordgradientcoord.z;
#endif


#ifdef GRADIENT_COMPLEX
	// Apply a scale and bias based on the current texture width to fall on pixel centers
	// Make sure to update this if we change the gradient resolution
	const float gradientTextureWidth = 1024.0;
	const float gradientScale = (gradientTextureWidth - 1.0) / gradientTextureWidth;
	const float gradientBias = 0.5 / gradientTextureWidth;
	float gradientCoord = clamp(gradientposition, 0.0, 1.0) * gradientScale + gradientBias;
	texcol *= texture1D ( Texture3, gradientCoord );

#elif defined(GRADIENT_TWOSTOP)
	texcol *= mix(color0, color1, clamp(gradientposition, 0.0, 1.0));
#else
	texcol *= color0;
#endif

	// we have a complicated challenge with corners, we must support the following:
	// 1. independent radii (every corner is an ellipse) - this is quite challenging, and requires computing the nearest point
	// 2. per pixel antialiasing (every pixel is computing a distance function) - this is challenging with independent radii and is why we need the nearest point
	// 3. border rendering - the quad can have a border of specified thickness and color, it may have inner and outer radius to achieve this 'wide line' effect
	// in light of these requirements (especially the independent radii) the math is quite lengthy...
	//
	// input:
	// corner coords : position in 0-1 space (the unit circle), negative space is clamped (thus we have each corner as an infinite quadrant of space with a rounded corner)
	// corner radii : to scale the 0-1 unit circle space to pixel resolution for antialiasing purposes (our antialiased distance function must evaluate at pixel scale for proper results)
	//
	// output:
	// opacity : opacity value for each corner space (infinite quadrant with rounded corner)
	//
	// method:
	// clamp cornercoord values to positive range (as each one represents the bottom right corner case), these resulting values may exceed length 1 for pixels off the quadrant or outside the corner circle
	// calculate length of the clamped coords and clamp the length to not be outside the unit circle (distance <= 1), these are the 'nearest length' values
	// then use these nearest length values to scale the corner coords to get the nearest point on the filled circle (any position inside the circle will result in coords 0,0)
	// then subtract the nearest coords from the current coords to get a proper offset from the circle, and scale them by the radii to get screen coordinates
	// take the length of the screen coordinates (distance from the screen space ellipse).
	// clamp the screen distances to 0-1 range and invert as needed to get opacity values(for outer corners we take the 1-dist, for inner corners we take the dist as-is).
	// combine all opacity values

#ifdef USEINNERCORNER
	// innercorners - on the border we mix to bordercolor
	vec4 innercorners0 = max(innercornercoord0, vec4(0.0, 0.0, 0.0, 0.0));
	vec4 innercorners1 = max(innercornercoord1, vec4(0.0, 0.0, 0.0, 0.0));
	vec4 innercornerslength1 = vec4(length(innercorners0.xy), length(innercorners0.zw), length(innercorners1.xy), length(innercorners1.zw));
	vec4 innercornerslength = max( innercornerslength1, vec4(0.000001, 0.000001, 0.000001, 0.000001));
	vec4 innercornerslengthmax = min(innercornerslength, vec4(1.0, 1.0, 1.0, 1.0));
	vec4 innercornersscale = innercornerslengthmax / innercornerslength;
	vec4 innercorners0nearest = innercorners0 * innercornersscale.xxyy;
	vec4 innercorners1nearest = innercorners1 * innercornersscale.zzww;
	vec4 innercorners0screen = (innercorners0 - innercorners0nearest) * innercornerradii0;
	vec4 innercorners1screen = (innercorners1 - innercorners1nearest) * innercornerradii1;
	vec4 innercornerdists = vec4(length(innercorners0screen.xy), length(innercorners0screen.zw), length(innercorners1screen.xy), length(innercorners1screen.zw));
	vec4 innercorneropacities = vec4(1.0, 1.0, 1.0, 1.0) - clamp(innercornerdists, 0.0, 1.0);
	float innercorneropacity = 1.0 - innercorneropacities.x * innercorneropacities.y * innercorneropacities.z * innercorneropacities.w;
	texcol = mix(texcol, bordercolor, innercorneropacity);
#endif

#ifdef USEOUTERCORNER
	// outercorners - on the outside we fade to nothing
	vec4 outercorners0 = max(outercornercoord0, vec4(0.0, 0.0, 0.0, 0.0));
	vec4 outercorners1 = max(outercornercoord1, vec4(0.0, 0.0, 0.0, 0.0));
	vec4 outercornerslength1 = vec4(length(outercorners0.xy), length(outercorners0.zw), length(outercorners1.xy), length(outercorners1.zw));
	vec4 outercornerslength = max( outercornerslength1, vec4(0.000001, 0.000001, 0.000001, 0.000001));
	vec4 outercornerslengthmin = min(outercornerslength, vec4(1.0, 1.0, 1.0, 1.0));
	vec4 outercornersscale = outercornerslengthmin / outercornerslength;
	vec4 outercorners0nearest = outercorners0 * outercornersscale.xxyy;
	vec4 outercorners1nearest = outercorners1 * outercornersscale.zzww;
	vec4 outercorners0screen = (outercorners0 - outercorners0nearest) * outercornerradii0;
	vec4 outercorners1screen = (outercorners1 - outercorners1nearest) * outercornerradii1;
	vec4 outercornerdists = vec4(length(outercorners0screen.xy), length(outercorners0screen.zw), length(outercorners1screen.xy), length(outercorners1screen.zw));
	vec4 outercorneropacities =  vec4( 1.0, 1.0, 1.0, 1.0 ) - clamp( outercornerdists, 0.000001, 0.99999999);
	float outercorneropacity = outercorneropacities.x * outercorneropacities.y * outercorneropacities.z * outercorneropacities.w;
	texcol *= outercorneropacity;
#endif

#ifdef USEOPACITYMASK
	texcol = texcol * ( 1.0 - g_OpacityMaskOpacity ) + texcol*texture2D( Texture1, opacitytexcoord.st ).a*g_OpacityMaskOpacity;
#endif

	gl_FragColor = texcol;
}

