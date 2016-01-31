#version 120
#extension GL_ARB_texture_rectangle : require
#extension GL_ARB_texture_rectangle : enable

uniform mat4 g_MatTransform;
uniform float g_viewportWidth;
uniform float g_viewportHeight;
varying vec4 texcoordgradientcoord;// texcoord and position in gradient space (where length()=0 is color0, length()=1 is color1, values in between predictably linear interpolate, values outside are clamped)
varying vec4 outercornercoord0; // coords in the rounded corner space for top left and top right
varying vec4 outercornercoord1; // coords in the rounded corner space for bottom left and bottom right
varying vec4 innercornercoord0; // coords in the rounded corner space for top left and top right
varying vec4 innercornercoord1; // coords in the rounded corner space for bottom left and bottom right
varying vec4 color0; // gradient start color (stop position = 0.0)
varying vec4 color1; // gradient end color (stop position = 1.0)
varying vec4 opacitytexcoord; // texcoord for opacitymask


void main()
{
	gl_Position =  g_MatTransform * gl_Vertex;
	gl_Position.x = ( gl_Position.x / ( g_viewportWidth/2.0 ) ) - 1;
	gl_Position.y = -(  gl_Position.y / ( g_viewportHeight/2.0 ) ) + 1;
	gl_Position.z = 0.0f;
	
	texcoordgradientcoord = gl_MultiTexCoord0;
	outercornercoord0 = gl_MultiTexCoord1;
	outercornercoord1 = gl_MultiTexCoord2;
	color0 = gl_MultiTexCoord3;
	color1 = gl_MultiTexCoord4;
	innercornercoord0 = gl_MultiTexCoord5;
	innercornercoord1 = gl_MultiTexCoord6;
	opacitytexcoord = gl_MultiTexCoord7;
}
