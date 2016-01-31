#version 120
#extension GL_ARB_texture_rectangle : require
#extension GL_ARB_texture_rectangle : enable

uniform mat4 g_MatTransform;
uniform float g_viewportWidth;
uniform float g_viewportHeight;
varying vec4 tex; 
varying vec4 tex1; 
varying vec4 color; 

void main()
{
	gl_Position =  g_MatTransform * gl_Vertex;
	gl_Position.x = ( gl_Position.x / ( g_viewportWidth/2.0 ) ) - 1;
	gl_Position.y = -(  gl_Position.y / ( g_viewportHeight/2.0 ) ) + 1;
	
	gl_Position.z = 0.0f;
	
	color = gl_Color;
	tex = gl_MultiTexCoord0;
	tex1 = gl_MultiTexCoord1;
	tex1.t = 1 - tex1.t; // flip the texture over the y axis to account for OGL being upside down
}